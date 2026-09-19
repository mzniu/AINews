from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.account import UsercenterAccount
from app.models.workspace import Workspace


def get_or_create_personal_workspace(
    db: Session,
    usercenter_user_id: str,
    *,
    email: str | None = None,
) -> Workspace:
    uid = usercenter_user_id.strip()
    account = db.get(UsercenterAccount, uid)
    if account is None:
        account = UsercenterAccount(usercenter_user_id=uid, email=email)
        db.add(account)
        db.flush()
    elif email and account.email != email:
        account.email = email

    workspace = (
        db.query(Workspace)
        .filter_by(owner_usercenter_id=uid, type="personal")
        .first()
    )
    if workspace is not None:
        return workspace

    workspace = Workspace(
        id=str(uuid.uuid4()),
        type="personal",
        name="Personal",
        owner_usercenter_id=uid,
    )
    db.add(workspace)
    db.flush()
    return workspace
