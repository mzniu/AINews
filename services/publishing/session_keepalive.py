"""Periodic session refresh to extend platform login validity."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session, sessionmaker

from services.publishing.browser_session import open_adapter_browser
from services.publishing.registry import (
    PlatformDisabledError,
    PlatformNotFoundError,
    get_adapter,
    get_platform_config,
    load_publishing_yaml,
)
from src.db.models.publishing import PublisherAccount


def load_session_keepalive_config(yaml: dict[str, Any] | None = None) -> dict[str, Any]:
    data = yaml or load_publishing_yaml()
    defaults = data.get("defaults") or {}
    cfg = defaults.get("session_keepalive") or {}
    platforms = cfg.get("platforms")
    if not platforms:
        platforms = ["wechat_channels"]
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "interval_hours": float(cfg.get("interval_hours", 4)),
        "platforms": list(platforms),
        "headless": bool(cfg.get("headless", False)),
    }


def _visit_urls_for_platform(platform_id: str, cfg: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    qr_profile = cfg.get("qr_profile") or {}
    post_login = str(qr_profile.get("post_login_url") or "").strip()
    creator = str(cfg.get("creator_url") or "").strip()
    if post_login:
        urls.append(post_login)
    if creator and creator not in urls:
        urls.append(creator)
    if not urls:
        login_url = str(cfg.get("login_url") or "").strip()
        if login_url:
            urls.append(login_url)
    return urls


def _is_login_page(url: str, *, excludes: list[str]) -> bool:
    lower = (url or "").lower()
    return any(token in lower for token in excludes)


def refresh_platform_session(
    platform_id: str,
    session_path: Path,
    *,
    headless: bool | None = None,
) -> str:
    """Visit creator pages with the account profile and refresh encrypted backup."""
    adapter = get_adapter(platform_id)
    if hasattr(adapter, "refresh_session"):
        return adapter.refresh_session(session_path, headless=headless if headless is not None else False)

    cfg = get_platform_config(platform_id)
    excludes = list((cfg.get("qr_profile") or {}).get("success_url_excludes") or ["login", "passport"])
    visit_urls = _visit_urls_for_platform(platform_id, cfg)
    if not visit_urls:
        return adapter.validate_session(session_path)

    from services.publishing.human_interaction import human_idle_on_page
    from services.publishing.human_pacing import human_pause

    try:
        with open_adapter_browser(session_path, mode="keepalive", headless=headless) as sess:
            page = sess.page
            active = False
            for url in visit_urls:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                human_pause(page, "page_load")
                human_idle_on_page(page, moves=1)
                if not _is_login_page(page.url, excludes=excludes):
                    active = True
                    break
            if not active:
                return "expired"
        return "active"
    except Exception as exc:
        logger.warning("Session keepalive failed for %s: %s", platform_id, exc)
        return adapter.validate_session(session_path)


def _persist_account_status(
    session: Session,
    account: PublisherAccount,
    status: str,
    *,
    refreshed: bool,
) -> None:
    now = datetime.utcnow()
    if status in ("active", "expired"):
        account.status = status
    account.updated_at = now
    if refreshed and status == "active":
        account.last_login_at = now
    session.flush()


def run_session_keepalive(session_factory: sessionmaker) -> dict[str, Any]:
    cfg = load_session_keepalive_config()
    if not cfg.get("enabled", True):
        return {"skipped": True, "reason": "disabled"}

    platform_ids = set(cfg.get("platforms") or [])
    summary: dict[str, Any] = {
        "checked": 0,
        "refreshed": 0,
        "expired": 0,
        "errors": 0,
        "accounts": [],
    }

    with session_factory() as session:
        accounts = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform.in_(platform_ids))
            .filter(PublisherAccount.status.in_(("active", "unknown")))
            .all()
        )
        account_rows = [
            {
                "id": account.id,
                "platform": account.platform,
                "session_path": account.session_path,
            }
            for account in accounts
        ]

    from src.utils.config import Config

    for row in account_rows:
        summary["checked"] += 1
        session_file = Config.ROOT_DIR / row["session_path"]
        if not session_file.is_file():
            with session_factory() as session:
                account = session.get(PublisherAccount, row["id"])
                if account is not None:
                    _persist_account_status(session, account, "expired", refreshed=False)
                    session.commit()
            summary["expired"] += 1
            summary["accounts"].append(
                {"account_id": row["id"], "platform": row["platform"], "status": "expired"}
            )
            continue

        try:
            status = refresh_platform_session(
                row["platform"],
                session_file,
                headless=bool(cfg.get("headless", False)),
            )
        except (PlatformNotFoundError, PlatformDisabledError) as exc:
            logger.warning("Keepalive skip %s: %s", row["id"], exc)
            summary["errors"] += 1
            continue
        except Exception as exc:
            logger.exception("Keepalive error account=%s: %s", row["id"], exc)
            summary["errors"] += 1
            continue

        with session_factory() as session:
            account = session.get(PublisherAccount, row["id"])
            if account is not None:
                _persist_account_status(
                    session,
                    account,
                    status,
                    refreshed=status == "active",
                )
                session.commit()

        if status == "active":
            summary["refreshed"] += 1
            logger.info("Session keepalive refreshed account=%s platform=%s", row["id"], row["platform"])
        elif status == "expired":
            summary["expired"] += 1
            logger.warning(
                "Session keepalive detected expired account=%s platform=%s",
                row["id"],
                row["platform"],
            )
        summary["accounts"].append(
            {"account_id": row["id"], "platform": row["platform"], "status": status}
        )

    return summary
