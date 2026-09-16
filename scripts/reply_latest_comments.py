"""Reply to the N newest eligible audience comments (live test).

Usage:
  python scripts/reply_latest_comments.py --limit 20
  python scripts/reply_latest_comments.py --limit 20 --platform douyin
  python scripts/reply_latest_comments.py --limit 20 --platform all --dry-run
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from services.publishing.browser_session import open_adapter_browser
from services.publishing.comment_reply.config import load_comment_reply_config
from services.publishing.comment_reply.decision import should_process_comment
from services.publishing.comment_reply.inline_helpers import merge_post_backlog, resolve_inline_reply_text
from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator
from services.publishing.comment_reply.platforms import post_id_from_row
from services.publishing.comment_reply.types import InboundComment
from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import CommentInbox, PublishJob, PublisherAccount
from src.utils.paths import resolve_data_path


def _sort_key(comment: InboundComment) -> datetime:
    return comment.commented_at or datetime.min


def _collect_candidates(
    *,
    session,
    account: PublisherAccount,
    post_rows: list[dict],
    comments_by_post: dict[str, list[InboundComment]],
    first_comments: set[str],
    lookback: datetime,
    retry_max: int,
) -> list[tuple[dict, InboundComment, object | None]]:
    candidates: list[tuple[dict, InboundComment, object | None]] = []
    for post_row in post_rows:
        post_id = post_id_from_row(account.platform, post_row)
        comments = comments_by_post.get(post_id) or []
        comments = merge_post_backlog(
            session,
            account=account,
            post_id=post_id,
            api_comments=comments,
            lookback=lookback,
        )
        for comment in comments:
            existing = (
                session.query(CommentInbox)
                .filter_by(
                    platform=account.platform,
                    platform_comment_id=comment.platform_comment_id,
                )
                .first()
            )
            decision = should_process_comment(
                comment,
                existing_row=existing,
                account_nickname=account.nickname,
                author_first_comments=first_comments,
                lookback=lookback,
                intent="inline",
                retry_max=retry_max,
            )
            if decision.process:
                candidates.append((post_row, comment, existing))
    candidates.sort(key=lambda item: _sort_key(item[1]), reverse=True)
    return candidates


def run_douyin(session_factory, account_id: str, *, limit: int, dry_run: bool) -> dict:
    from services.publishing.adapters.douyin_audience_reply import (
        activate_douyin_post_session,
        fetch_douyin_comments_for_post,
        reply_douyin_audience_comment_on_active_feed,
        scan_douyin_post_rows,
        _navigate_comment_hub,
    )

    cfg = load_comment_reply_config()
    lookback = datetime.utcnow() - timedelta(hours=int(cfg["lookback_hours"]))

    with session_factory() as session:
        account = session.get(PublisherAccount, account_id)
        if account is None:
            raise ValueError(f"account_not_found:{account_id}")
        first_comments = {
            str(row.first_comment_text or "").strip()
            for row in session.query(PublishJob)
            .filter_by(account_id=account.id, status="published")
            .all()
            if str(row.first_comment_text or "").strip()
        }
        job_by_post = {
            str(row.platform_post_id): row
            for row in session.query(PublishJob)
            .filter_by(account_id=account.id, status="published")
            .all()
            if row.platform_post_id
        }
        session_path = resolve_data_path(account.session_path)
        nickname = account.nickname

    comments_by_post: dict[str, list[InboundComment]] = {}
    post_rows: list[dict] = []

    with open_adapter_browser(session_path, mode="keepalive", headless=False) as sess:
        page = sess.page
        _navigate_comment_hub(page)
        post_rows = scan_douyin_post_rows(page, max_posts=int(cfg["max_scan_posts"]))
        for post_row in post_rows:
            if int(post_row.get("comment_count") or 0) <= 0:
                continue
            post_id = post_id_from_row("douyin", post_row)
            session_ctx = activate_douyin_post_session(page, post_row=post_row)
            if not session_ctx.feed_active:
                logger.warning("跳过作品（无法进入评论页）: {}", post_row.get("title"))
                continue
            comments_by_post[post_id] = fetch_douyin_comments_for_post(
                page,
                video_id=post_id,
                post_title=str(post_row.get("title") or ""),
                account_nickname=nickname,
            )

        with session_factory() as session:
            account = session.get(PublisherAccount, account_id)
            candidates = _collect_candidates(
                session=session,
                account=account,
                post_rows=post_rows,
                comments_by_post=comments_by_post,
                first_comments=first_comments,
                lookback=lookback,
                retry_max=int(cfg["retry_max"]),
            )[:limit]

            logger.info("待回复（最新 {} 条）: {}", min(limit, len(candidates)), len(candidates))
            for idx, (_, comment, _) in enumerate(candidates, 1):
                ts = comment.commented_at.isoformat(sep=" ", timespec="seconds") if comment.commented_at else "?"
                logger.info(
                    "  {:02d}. {} | {} | {}",
                    idx,
                    ts,
                    (comment.author_name or "?")[:12],
                    (comment.content or "")[:40],
                )

            if dry_run:
                return {"dry_run": True, "candidates": len(candidates)}

            orchestrator = CommentReplyOrchestrator(session_factory)
            sent = 0
            failed = 0
            by_post: dict[str, list[tuple[dict, InboundComment, object | None]]] = defaultdict(list)
            for post_row, comment, existing in candidates:
                by_post[post_id_from_row("douyin", post_row)].append((post_row, comment, existing))

            for post_id, items in by_post.items():
                post_row = items[0][0]
                post_title = str(post_row.get("title") or "").strip()
                job = job_by_post.get(post_id)
                session_ctx = activate_douyin_post_session(page, post_row=post_row)
                if not session_ctx.feed_active:
                    failed += len(items)
                    continue
                for post_row, comment, existing in items:
                    session.commit()
                    try:
                        reply_text = resolve_inline_reply_text(
                            existing,
                            comment=comment,
                            post_title=post_title or (job.title if job else ""),
                            post_description=job.description if job else None,
                            audience_name=comment.author_name,
                            min_length=int(cfg["reply_min_length"]),
                            max_length=int(cfg["reply_max_length"]),
                        )
                    except Exception as exc:
                        logger.warning("生成回复失败 {}: {}", comment.platform_comment_id, exc)
                        failed += 1
                        continue

                    result = reply_douyin_audience_comment_on_active_feed(
                        page,
                        session=session_ctx,
                        comment=comment,
                        reply_text=reply_text,
                        account_nickname=nickname,
                    )
                    if result.success:
                        orchestrator._save_inline_outcome(
                            session,
                            existing=existing,
                            account=account,
                            comment=comment,
                            post_title=post_title,
                            job=job,
                            reply_text=reply_text,
                            success=True,
                        )
                        sent += 1
                        logger.info("已回复: {}", (comment.content or "")[:30])
                    else:
                        orchestrator._save_inline_outcome(
                            session,
                            existing=existing,
                            account=account,
                            comment=comment,
                            post_title=post_title,
                            job=job,
                            reply_text=reply_text,
                            success=False,
                            error_message=result.error_message or "send_failed",
                        )
                        failed += 1
                        logger.warning("回复失败 {}: {}", comment.platform_comment_id, result.error_message)
                    session.commit()
                    pause = int(cfg.get("pause_between_replies_sec") or 0)
                    if pause > 0:
                        time.sleep(pause)

            return {"sent": sent, "failed": failed, "candidates": len(candidates)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--platform", default="douyin", choices=["douyin", "all"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    factory = get_session_factory()
    cfg = load_comment_reply_config()

    with factory() as session:
        query = session.query(PublisherAccount).filter(PublisherAccount.status == "active")
        if args.platform == "douyin":
            query = query.filter(PublisherAccount.platform == "douyin")
        else:
            query = query.filter(PublisherAccount.platform.in_(cfg["platforms"]))
        accounts = query.all()

    if not accounts:
        print("No active accounts found")
        return 1

    totals = {"sent": 0, "failed": 0, "candidates": 0}
    remaining = args.limit

    for account in accounts:
        if remaining <= 0:
            break
        if account.platform != "douyin":
            logger.warning("跳过平台 {}（本脚本当前仅实现 douyin 实测）", account.platform)
            continue
        logger.info("开始测试账号 {} ({})", account.nickname, account.platform)
        result = run_douyin(
            factory,
            account.id,
            limit=remaining,
            dry_run=args.dry_run,
        )
        if result.get("dry_run"):
            print(result)
            return 0
        totals["sent"] += int(result.get("sent") or 0)
        totals["failed"] += int(result.get("failed") or 0)
        totals["candidates"] += int(result.get("candidates") or 0)
        remaining = max(0, args.limit - totals["sent"] - totals["failed"])

    print(
        f"完成: 目标={args.limit} 候选={totals['candidates']} "
        f"成功={totals['sent']} 失败={totals['failed']}"
    )
    return 0 if totals["failed"] == 0 or totals["sent"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
