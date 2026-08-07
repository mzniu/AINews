"""Check publisher account session validity against the platform."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from services.ingestion.db_retry import run_with_sqlite_retry
from services.publishing.registry import PlatformDisabledError, PlatformNotFoundError, get_adapter
from src.db.engine import session_scope
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

_STATUS_MESSAGES = {
    "active": "会话有效，可正常发布",
    "expired": "会话已过期，请重新扫码登录",
    "unknown": "无法确认会话状态，请稍后重试或重新登录",
}


def _persist_status(account_id: str, status: str) -> None:
    def _update() -> None:
        with session_scope() as db:
            account = db.get(PublisherAccount, account_id)
            if account is None:
                return
            if status in ("active", "expired"):
                account.status = status
            account.updated_at = datetime.utcnow()

    run_with_sqlite_retry(_update)


def check_account_status(account_id: str) -> dict:
    with session_scope() as db:
        account = db.get(PublisherAccount, account_id)
        if account is None:
            raise ValueError("账号不存在")

        info = {
            "account_id": account.id,
            "nickname": account.nickname,
            "platform": account.platform,
            "status": account.status,
        }
        session_path = Config.ROOT_DIR / account.session_path

    if not session_path.is_file():
        _persist_status(account_id, "expired")
        return {
            "success": True,
            "account_id": info["account_id"],
            "status": "expired",
            "message": "会话文件缺失，请重新扫码登录",
            "nickname": info["nickname"],
            "platform": info["platform"],
        }

    try:
        adapter = get_adapter(info["platform"])
    except (PlatformNotFoundError, PlatformDisabledError) as exc:
        return {
            "success": False,
            "account_id": info["account_id"],
            "status": info["status"],
            "message": str(exc),
            "nickname": info["nickname"],
            "platform": info["platform"],
        }

    # validate_session opens Playwright; run only after DB session is closed.
    session_status = adapter.validate_session(session_path)

    if session_status in ("active", "expired"):
        _persist_status(account_id, session_status)

    return {
        "success": True,
        "account_id": info["account_id"],
        "status": session_status,
        "message": _STATUS_MESSAGES.get(session_status, _STATUS_MESSAGES["unknown"]),
        "nickname": info["nickname"],
        "platform": info["platform"],
    }
