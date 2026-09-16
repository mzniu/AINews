"""Unblock a stuck publish job and optionally retry."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / "AppData/Roaming/AINews"
DB = DATA_DIR / "ainews.db"
LOCK = DATA_DIR / ".playwright.lock"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", default="bad1e8abf934491a892e18f4027c7279")
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()

    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, status, title FROM publish_jobs WHERE id=?",
        (args.job_id,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"job not found: {args.job_id}")
    print("before:", row)

    if row[1] in {"uploading", "processing"}:
        cur.execute(
            """
            UPDATE publish_jobs
            SET status='failed',
                finished_at=?,
                error_message=?
            WHERE id=?
            """,
            (
                now,
                "视频号上传步骤超时卡住（已手动解除，可重试）",
                args.job_id,
            ),
        )
        conn.commit()
        print("marked failed")

    if args.retry:
        cur.execute(
            """
            UPDATE publish_jobs
            SET status='pending',
                started_at=NULL,
                finished_at=NULL,
                error_message=NULL
            WHERE id=?
            """,
            (args.job_id,),
        )
        conn.commit()
        print("reset to pending for retry")

    conn.close()
    if LOCK.exists():
        LOCK.unlink()
        print("removed playwright lock")


if __name__ == "__main__":
    main()
