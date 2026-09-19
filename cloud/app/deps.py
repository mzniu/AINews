from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt import JWTAuthError, decode_access_token
from app.config import Settings, get_settings
from app.database import get_db
from app.models.workspace import Workspace
from app.services.tenant import get_or_create_personal_workspace

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentContext:
    usercenter_user_id: str
    workspace: Workspace
    email: str | None = None


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CurrentContext:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except JWTAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    user_id = str(claims.get("sub"))
    email = claims.get("email")
    if isinstance(email, str):
        email = email.strip() or None
    else:
        email = None
    workspace = get_or_create_personal_workspace(db, user_id, email=email)
    return CurrentContext(
        usercenter_user_id=user_id,
        workspace=workspace,
        email=email,
    )
