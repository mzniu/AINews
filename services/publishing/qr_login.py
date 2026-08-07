"""QR login session processing for publish-worker."""
from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy.orm import Session, sessionmaker

from services.publishing.adapters.base import QrLoginContext
from services.publishing.registry import get_adapter, get_platform_config, load_publishing_yaml
from src.db.models.publishing import PublisherAccount, QrLoginSession
from src.utils.config import Config


def process_qr_session(session_factory: sessionmaker, session_id: str) -> None:
    with session_factory() as session:
        row = session.get(QrLoginSession, session_id)
        if row is None or row.status not in {"pending", "processing"}:
            return
        row.status = "processing"
        row.started_at = datetime.utcnow()
        session.commit()
        platform = row.platform
        purpose = row.purpose
        account_id = row.account_id

    try:
        cfg = get_platform_config(platform)
        defaults = load_publishing_yaml().get("defaults") or {}
        adapter = get_adapter(platform)
        qr_dir = Config.ROOT_DIR / "data" / "publish" / "qr"
        ctx = QrLoginContext(
            session_id=session_id,
            login_url=cfg.get("login_url", ""),
            qr_dir=qr_dir,
            qr_timeout_sec=int(defaults.get("qr_timeout_sec", 120)),
        )
        result = adapter.run_qr_login_flow(ctx)

        with session_factory() as session:
            row = session.get(QrLoginSession, session_id)
            if row is None:
                return
            row.qr_image_path = result.qr_image_path
            if result.status == "confirmed" and result.storage_state_json and result.account_info:
                account = _upsert_account(
                    session,
                    platform=platform,
                    purpose=purpose,
                    existing_account_id=account_id,
                    account_info=result.account_info,
                    storage_state_json=result.storage_state_json,
                )
                row.status = "confirmed"
                row.account_id = account.id
                row.finished_at = datetime.utcnow()
            else:
                row.status = result.status
                row.error_message = result.error_message
                row.finished_at = datetime.utcnow()
            session.commit()
    except Exception as exc:
        logger.exception(f"QR session {session_id} failed: {exc}")
        with session_factory() as session:
            row = session.get(QrLoginSession, session_id)
            if row:
                row.status = "failed"
                row.error_message = str(exc)
                row.finished_at = datetime.utcnow()
                session.commit()


def _upsert_account(
    session: Session,
    *,
    platform: str,
    purpose: str,
    existing_account_id: str | None,
    account_info,
    storage_state_json: bytes,
) -> PublisherAccount:
    now = datetime.utcnow()
    account: PublisherAccount | None = None
    if purpose == "refresh" and existing_account_id:
        account = session.get(PublisherAccount, existing_account_id)
    if account is None:
        account = (
            session.query(PublisherAccount)
            .filter_by(platform=platform, platform_uid=account_info.platform_uid)
            .first()
        )
    if account is None:
        account = PublisherAccount(
            platform=platform,
            platform_uid=account_info.platform_uid,
            nickname=account_info.nickname,
            avatar_url=account_info.avatar_url,
            session_path="",
        )
        session.add(account)
        session.flush()

    session_path = Config.ROOT_DIR / "data" / "publish" / "sessions" / f"{account.id}.enc"
    adapter = get_adapter(platform)
    adapter.persist_storage_state(session_path, storage_state_json)
    account.session_path = f"data/publish/sessions/{account.id}.enc"
    account.nickname = account_info.nickname
    account.avatar_url = account_info.avatar_url
    account.platform_uid = account_info.platform_uid
    account.status = "active"
    account.last_login_at = now
    account.updated_at = now
    return account


def create_qr_session(
    session: Session,
    *,
    platform: str,
    purpose: str = "create",
    account_id: str | None = None,
) -> QrLoginSession:
    defaults = load_publishing_yaml().get("defaults") or {}
    qr_timeout = int(defaults.get("qr_timeout_sec", 120))
    row = QrLoginSession(
        platform=platform,
        purpose=purpose,
        account_id=account_id,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(seconds=qr_timeout),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
