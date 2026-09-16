"""Clear comment inbox rows (default: pending/failed wechat_channels)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from src.db.engine import get_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear comment inbox rows")
    parser.add_argument(
        "--platform",
        default="wechat_channels",
        help="Platform to clear (default: wechat_channels)",
    )
    parser.add_argument(
        "--status",
        action="append",
        default=["pending_approval", "failed"],
        help="Statuses to delete (repeatable)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Delete all rows for the platform regardless of status",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show counts only, do not delete",
    )
    args = parser.parse_args()

    factory = get_session_factory()
    with factory() as session:
        if args.all:
            count = session.execute(
                text("SELECT COUNT(*) FROM comment_inbox WHERE platform = :platform"),
                {"platform": args.platform},
            ).scalar()
            print(f"would delete {count} rows for platform={args.platform} (all statuses)")
            if not args.dry_run and count:
                session.execute(
                    text("DELETE FROM comment_inbox WHERE platform = :platform"),
                    {"platform": args.platform},
                )
                session.commit()
                print(f"deleted {count} rows")
            return

        statuses = tuple(args.status)
        placeholders = ", ".join(f":s{i}" for i in range(len(statuses)))
        params = {f"s{i}": status for i, status in enumerate(statuses)}
        params["platform"] = args.platform
        count = session.execute(
            text(
                f"""
                SELECT COUNT(*) FROM comment_inbox
                WHERE platform = :platform AND status IN ({placeholders})
                """
            ),
            params,
        ).scalar()
        print(
            f"would delete {count} rows for platform={args.platform} status in {list(statuses)}"
        )
        if not args.dry_run and count:
            session.execute(
                text(
                    f"""
                    DELETE FROM comment_inbox
                    WHERE platform = :platform AND status IN ({placeholders})
                    """
                ),
                params,
            )
            session.commit()
            print(f"deleted {count} rows")


if __name__ == "__main__":
    main()
