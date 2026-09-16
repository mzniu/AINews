#!/usr/bin/env python3
"""Migrate existing encrypted storage_state sessions to persistent Chrome profiles."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from services.publishing.browser_profile import (
    BROWSER_PROFILE_VERSION,
    is_profile_initialized,
    migrate_account_session,
    profile_path_for_account,
    resolve_profile_dir,
)
from services.publishing.registry import get_platform_config, load_publishing_yaml
from src.db.engine import init_db, session_scope
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config


def _post_login_url(platform: str) -> str | None:
    try:
        cfg = get_platform_config(platform)
    except Exception:
        return None
    qr_profile = cfg.get("qr_profile") or {}
    return str(qr_profile.get("post_login_url") or cfg.get("creator_url") or "").strip() or None


def migrate_accounts(*, dry_run: bool = False, account_id: str | None = None) -> dict[str, int]:
    init_db()
    stats = {"checked": 0, "skipped": 0, "migrated": 0, "failed": 0}
    with session_scope() as session:
        query = session.query(PublisherAccount)
        if account_id:
            query = query.filter(PublisherAccount.id == account_id)
        accounts = query.all()
        rows = [
            {
                "id": account.id,
                "platform": account.platform,
                "session_path": account.session_path,
                "browser_profile_path": account.browser_profile_path,
            }
            for account in accounts
        ]

    for row in rows:
        stats["checked"] += 1
        profile_dir = resolve_profile_dir(row["id"])
        if is_profile_initialized(profile_dir):
            stats["skipped"] += 1
            logger.info("Skip account {}: profile already exists", row["id"])
            continue
        session_file = Config.ROOT_DIR / row["session_path"]
        if not session_file.is_file():
            stats["failed"] += 1
            logger.warning("Skip account {}: session file missing ({})", row["id"], session_file)
            continue
        if dry_run:
            logger.info("Would migrate account {} from {}", row["id"], session_file)
            stats["migrated"] += 1
            continue
        try:
            migrate_account_session(
                row["id"],
                session_file,
                post_login_url=_post_login_url(row["platform"]),
            )
            with session_scope() as session:
                account = session.get(PublisherAccount, row["id"])
                if account is not None:
                    account.browser_profile_path = profile_path_for_account(row["id"])
                    account.browser_profile_version = BROWSER_PROFILE_VERSION
            stats["migrated"] += 1
            logger.info("Migrated account {} -> {}", row["id"], profile_dir)
        except Exception as exc:
            stats["failed"] += 1
            logger.exception("Failed to migrate account {}: {}", row["id"], exc)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate publish sessions to Chrome profiles")
    parser.add_argument("--account-id", help="Migrate a single account id")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without launching browser")
    args = parser.parse_args()
    _ = load_publishing_yaml()
    stats = migrate_accounts(dry_run=args.dry_run, account_id=args.account_id)
    logger.info("Migration summary: {}", stats)
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
