"""Backfill comment_inbox.post_context_json for existing pending rows."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from services.publishing.adapters.wechat_channels_audience_reply import capture_wechat_hub_feed_text
from services.publishing.browser_session import open_adapter_browser
from services.publishing.comment_reply.post_context import (
    build_feed_match_spec_from_job,
    build_wechat_inbox_post_context,
    dumps_post_context,
)
from src.db.engine import get_session_factory
from src.db.models.publishing import CommentInbox, PublishJob, PublisherAccount
from src.utils.config import Config


def main() -> None:
    factory = get_session_factory()
    updated = 0
    with factory() as session:
        rows = (
            session.query(CommentInbox)
            .filter(
                CommentInbox.platform == "wechat_channels",
                CommentInbox.status.in_(("pending_approval", "failed")),
            )
            .all()
        )
        by_account: dict[str, list[CommentInbox]] = {}
        for row in rows:
            by_account.setdefault(row.account_id, []).append(row)

        for account_id, inbox_rows in by_account.items():
            account = session.get(PublisherAccount, account_id)
            if account is None:
                continue
            export_ids = sorted({row.platform_post_id for row in inbox_rows if row.platform_post_id})
            jobs = {
                str(job.platform_post_id): job
                for job in session.query(PublishJob)
                .filter(
                    PublishJob.account_id == account_id,
                    PublishJob.platform_post_id.in_(export_ids),
                )
                .all()
                if job.platform_post_id
            }
            session_path = Config.ROOT_DIR / account.session_path
            with open_adapter_browser(session_path, mode="keepalive", headless=False) as sess:
                page = sess.page
                for export_id in export_ids:
                    job = jobs.get(export_id)
                    post_title = str(job.title if job and job.title else "")
                    feed_match_spec = build_feed_match_spec_from_job(
                        session,
                        job,
                        post_title=post_title,
                    )
                    hub_feed_text = capture_wechat_hub_feed_text(
                        page,
                        export_id,
                        feed_match_spec=feed_match_spec,
                    )
                    post_row = {
                        "export_id": export_id,
                        "title": post_title,
                        "hub_feed_text": hub_feed_text,
                    }
                    ctx = build_wechat_inbox_post_context(
                        post_row=post_row,
                        job=job,
                        session=session,
                    )
                    payload = dumps_post_context(ctx)
                    for row in inbox_rows:
                        if row.platform_post_id != export_id:
                            continue
                        row.post_context_json = payload
                        updated += 1
                    logger.info(
                        "backfill export_id={} hub={}",
                        export_id[-24:],
                        (hub_feed_text or "")[:80],
                    )
            session.commit()
    print({"updated": updated})


if __name__ == "__main__":
    main()
