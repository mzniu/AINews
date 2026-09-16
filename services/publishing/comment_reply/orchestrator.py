"""Scan and approve audience comment replies."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from loguru import logger

from sqlalchemy.orm import Session, sessionmaker



from services.publishing.browser_session import open_adapter_browser

from services.publishing.adapters.douyin_audience_reply import fetch_douyin_comments_for_post
from services.publishing.adapters.kuaishou_audience_reply import (
    activate_kuaishou_post_session,
    fetch_kuaishou_comments_for_post,
    reply_kuaishou_audience_comment_on_active_feed,
    scan_kuaishou_post_rows,
)
from services.publishing.adapters.wechat_channels_audience_reply import (
    activate_wechat_post_session,
    fetch_wechat_comments_for_post,
    fetch_wechat_post_rows,
    reply_wechat_audience_comment_on_active_feed,
)
from services.publishing.adapters.wechat_channels_comment import _navigate_comment_hub
from services.publishing.adapters.creator_comment_helpers import dismiss_overlays
from services.publishing.comment_reply.config import load_comment_reply_config
from services.publishing.comment_reply.decision import should_process_comment

from services.publishing.comment_reply.inline_helpers import (
    first_processable_comment_content,
    merge_post_backlog,
    resolve_inline_reply_text,
)

from services.publishing.comment_reply.filters import should_skip_comment

from services.publishing.comment_reply.generation import generate_comment_reply, validate_reply_text

from services.publishing.comment_reply.platforms import (

    SUPPORTED_PLATFORMS,

    post_id_from_row,

    reply_audience_comment,

    scan_account_comments,

)

from services.publishing.comment_reply.post_context import (
    build_feed_match_spec_from_job,
    build_wechat_inbox_post_context,
    dumps_post_context,
    parse_post_context,
    resolve_wechat_feed_match_spec,
)

from services.publishing.comment_reply.types import CommentReplyRunResult, InboundComment, ScanRunSummary

from src.db.models.publishing import CommentInbox, CommentReplyRun, PublishJob, PublisherAccount

from src.utils.config import Config
from src.utils.paths import resolve_data_path





class CommentReplyOrchestrator:

    def __init__(self, session_factory: sessionmaker) -> None:

        self.session_factory = session_factory



    def run_scheduled_cycle(self, *, force: bool = False) -> CommentReplyRunResult | None:

        cfg = load_comment_reply_config()

        if not force and not cfg.get("enabled"):

            logger.info("Comment reply cycle skipped: disabled")

            return None



        with self.session_factory() as session:

            run = CommentReplyRun(status="running", mode=str(cfg.get("mode", "approve")))

            session.add(run)

            session.commit()

            run_id = run.id



        summaries: list[ScanRunSummary] = []

        error_notes: list[str] = []

        try:

            summaries = self.scan_all_accounts(force=force)

            retry_summary = (

                self.retry_failed_replies()

                if cfg.get("retry_enabled")

                else {"retried": 0, "failed": 0}

            )

        except Exception as exc:

            logger.exception("Comment reply cycle failed: %s", exc)

            error_notes.append(str(exc))

            retry_summary = {"retried": 0, "failed": 0}



        with self.session_factory() as session:

            run = session.get(CommentReplyRun, run_id)

            if run is None:

                return None

            run.accounts_total = len(summaries)

            run.posts_scanned = sum(item.posts_scanned for item in summaries)

            run.comments_seen = sum(item.comments_seen for item in summaries)

            run.new_pending = sum(item.new_pending for item in summaries)

            run.auto_sent = sum(item.auto_sent for item in summaries)

            run.skipped = sum(item.skipped for item in summaries)

            run.failed = sum(item.errors for item in summaries) + int(retry_summary.get("failed") or 0)

            run.retried = int(retry_summary.get("retried") or 0)

            run.status = "failed" if error_notes else "success"

            run.error_summary = "; ".join(error_notes) if error_notes else None

            run.finished_at = datetime.utcnow()

            session.commit()

            return CommentReplyRunResult(
                id=run.id,
                status=run.status,
                mode=run.mode,
                accounts_total=run.accounts_total,
                posts_scanned=run.posts_scanned,
                comments_seen=run.comments_seen,
                new_pending=run.new_pending,
                auto_sent=run.auto_sent,
                skipped=run.skipped,
                failed=run.failed,
                retried=run.retried,
                error_summary=run.error_summary,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )



    def scan_all_accounts(self, *, force: bool = False) -> list[ScanRunSummary]:

        cfg = load_comment_reply_config()

        if not force and not cfg.get("enabled"):

            logger.info("Comment reply scan skipped: disabled")

            return []

        summaries: list[ScanRunSummary] = []

        with self.session_factory() as session:

            accounts = (

                session.query(PublisherAccount)

                .filter(

                    PublisherAccount.status == "active",

                    PublisherAccount.platform.in_(cfg["platforms"]),

                )

                .all()

            )

            accounts = sorted(
                accounts,
                key=lambda item: (
                    0
                    if item.platform == "wechat_channels"
                    else 1
                    if item.platform == "kuaishou"
                    else 2,
                    item.id,
                ),
            )

        for account in accounts:

            if account.platform not in SUPPORTED_PLATFORMS:

                logger.warning("Skip comment reply for unsupported platform %s", account.platform)

                continue

            logger.info(
                "Comment reply scan start account={} platform={}",
                account.id,
                account.platform,
            )

            try:

                summaries.append(self.scan_account(account.id))

            except Exception as exc:

                logger.exception("Comment reply scan failed for %s: %s", account.id, exc)

                summaries.append(

                    ScanRunSummary(

                        account_id=account.id,

                        platform=account.platform,

                        errors=1,

                    )

                )

            time.sleep(5)

        return summaries



    def scan_account_inline(self, account_id: str) -> ScanRunSummary:
        cfg = load_comment_reply_config()

        with self.session_factory() as session:
            account = session.get(PublisherAccount, account_id)
            if account is None or account.status != "active":
                raise ValueError(f"account_not_active:{account_id}")
            if account.platform != "wechat_channels":
                raise ValueError(f"inline_unsupported_platform:{account.platform}")

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
            match_specs_by_post: dict[str, dict[str, list[str]]] = {}
            for post_id, job in job_by_post.items():
                spec = build_feed_match_spec_from_job(session, job, post_title=str(job.title or ""))
                if spec:
                    match_specs_by_post[post_id] = spec

            session_path = resolve_data_path(account.session_path)
            account_nickname = account.nickname
            account_platform = account.platform

        summary = ScanRunSummary(account_id=account_id, platform=account_platform)
        lookback = datetime.utcnow() - timedelta(hours=int(cfg["lookback_hours"]))
        replies_this_run = 0

        with open_adapter_browser(session_path, mode="keepalive", headless=False) as sess:
            page = sess.page
            try:
                _navigate_comment_hub(page)
            except Exception as exc:
                summary.errors += 1
                logger.error("视频号评论中心打开失败 account={}: {}", account_id, exc)
                return summary

            post_rows = fetch_wechat_post_rows(page, limit=int(cfg["max_scan_posts"]))

            with self.session_factory() as session:
                account = session.get(PublisherAccount, account_id)
                if account is None:
                    raise ValueError(f"account_not_active:{account_id}")

                for post_row in post_rows:
                    if int(post_row.get("comment_count") or 0) <= 0:
                        continue

                    summary.posts_scanned += 1
                    post_id = post_id_from_row(account.platform, post_row)
                    post_title = str(post_row.get("title") or "").strip()
                    job = job_by_post.get(post_id)
                    post_context = build_wechat_inbox_post_context(
                        post_row=post_row,
                        job=job,
                        session=session,
                    )
                    post_context_json = dumps_post_context(post_context)
                    feed_match_spec = match_specs_by_post.get(post_id)
                    ctx = parse_post_context(post_context_json)

                    comments = fetch_wechat_comments_for_post(
                        page,
                        export_id=post_id,
                        post_title=post_title,
                        account_nickname=account_nickname,
                    )
                    comments = merge_post_backlog(
                        session,
                        account=account,
                        post_id=post_id,
                        api_comments=comments,
                        lookback=lookback,
                    )
                    activation_hint = first_processable_comment_content(
                        comments,
                        session=session,
                        account=account,
                        account_nickname=account_nickname,
                        author_first_comments=first_comments,
                        lookback=lookback,
                        retry_max=int(cfg["retry_max"]),
                    )

                    session_ctx = activate_wechat_post_session(
                        page,
                        post_row=post_row,
                        feed_match_spec=feed_match_spec,
                        post_description=str(ctx.get("description") or (job.description if job else "") or "") or None,
                        main_line1=str(ctx.get("main_line1") or ""),
                        main_line2=str(ctx.get("main_line2") or ""),
                        sub_title=str(ctx.get("sub_title") or ""),
                        sub_title2=str(ctx.get("sub_title2") or ""),
                        post_context_json=post_context_json,
                        skip_hub_navigate=True,
                        comment_content=activation_hint,
                    )

                    if not session_ctx.feed_active:
                        dismiss_overlays(page)
                        page.wait_for_timeout(1500)
                        session_ctx = activate_wechat_post_session(
                            page,
                            post_row=post_row,
                            feed_match_spec=feed_match_spec,
                            post_description=str(ctx.get("description") or (job.description if job else "") or "") or None,
                            main_line1=str(ctx.get("main_line1") or ""),
                            main_line2=str(ctx.get("main_line2") or ""),
                            sub_title=str(ctx.get("sub_title") or ""),
                            sub_title2=str(ctx.get("sub_title2") or ""),
                            post_context_json=post_context_json,
                            skip_hub_navigate=True,
                            comment_content=activation_hint,
                        )

                    if not session_ctx.feed_active:
                        summary.activation_failures += 1
                        for comment in comments:
                            existing = (
                                session.query(CommentInbox)
                                .filter_by(
                                    platform=account.platform,
                                    platform_comment_id=comment.platform_comment_id,
                                )
                                .first()
                            )
                            if existing is not None:
                                continue
                            self._insert_failed(
                                session,
                                account=account,
                                comment=comment,
                                post_title=post_title,
                                job=job,
                                error_message="work_not_found",
                                post_context_json=post_context_json,
                            )
                            summary.errors += 1
                        continue

                    replied_on_post = 0
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
                            account_nickname=account_nickname,
                            author_first_comments=first_comments,
                            lookback=lookback,
                            intent="inline",
                            retry_max=int(cfg["retry_max"]),
                        )
                        if not decision.process:
                            if decision.reason == "already_replied":
                                summary.already_replied += 1
                            if decision.record_skip and existing is None:
                                self._insert_skipped(
                                    session,
                                    account=account,
                                    comment=comment,
                                    post_title=post_title,
                                    job=job,
                                    reason=decision.reason or "skipped",
                                )
                                summary.skipped += 1
                            continue

                        summary.comments_seen += 1

                        if replies_this_run >= int(cfg["max_replies_per_run"]):
                            continue
                        if replied_on_post >= int(cfg["max_replies_per_post"]):
                            continue

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
                            summary.errors += 1
                            logger.warning(
                                "Comment reply generation failed for %s: %s",
                                comment.platform_comment_id,
                                exc,
                            )
                            continue

                        if comment.already_replied_by_author:
                            summary.already_replied += 1
                            self._insert_skipped(
                                session,
                                account=account,
                                comment=comment,
                                post_title=post_title,
                                job=job,
                                reason="already_replied",
                            )
                            summary.skipped += 1
                            continue

                        result = reply_wechat_audience_comment_on_active_feed(
                            page,
                            session=session_ctx,
                            comment=comment,
                            reply_text=reply_text,
                        )

                        if result.success:
                            self._save_inline_outcome(
                                session,
                                existing=existing,
                                account=account,
                                comment=comment,
                                post_title=post_title,
                                job=job,
                                reply_text=reply_text,
                                success=True,
                                post_context_json=post_context_json,
                            )
                            summary.auto_sent += 1
                            replies_this_run += 1
                            replied_on_post += 1
                        else:
                            self._save_inline_outcome(
                                session,
                                existing=existing,
                                account=account,
                                comment=comment,
                                post_title=post_title,
                                job=job,
                                reply_text=reply_text,
                                success=False,
                                error_message=result.error_message or "send_failed",
                                post_context_json=post_context_json,
                            )
                            summary.errors += 1

                        pause = int(cfg.get("pause_between_replies_sec") or 0)
                        if pause > 0:
                            time.sleep(pause)

                session.commit()

        logger.info(
            "Comment reply inline account={} posts={} seen={} sent={} skipped={} already_replied={} activation_failures={}",
            account_id,
            summary.posts_scanned,
            summary.comments_seen,
            summary.auto_sent,
            summary.skipped,
            summary.already_replied,
            summary.activation_failures,
        )
        return summary



    def scan_kuaishou_inline(self, account_id: str) -> ScanRunSummary:
        from services.publishing.adapters.kuaishou_audience_reply import _navigate_comment_hub
        from services.publishing.adapters.kuaishou_comment import (
            finalize_kuaishou_comment_page,
            prepare_kuaishou_comment_page,
            prune_kuaishou_extra_pages,
        )

        cfg = load_comment_reply_config()

        with self.session_factory() as session:
            account = session.get(PublisherAccount, account_id)
            if account is None or account.status != "active":
                raise ValueError(f"account_not_active:{account_id}")
            if account.platform != "kuaishou":
                raise ValueError(f"inline_unsupported_platform:{account.platform}")

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
            account_nickname = account.nickname
            account_platform = account.platform

        summary = ScanRunSummary(account_id=account_id, platform=account_platform)
        lookback = datetime.utcnow() - timedelta(hours=int(cfg["lookback_hours"]))
        replies_this_run = 0

        with open_adapter_browser(session_path, mode="keepalive", headless=False) as sess:
            page = prepare_kuaishou_comment_page(sess.context, sess.page)
            try:
                _navigate_comment_hub(page)
                dismiss_overlays(page)
                post_rows = scan_kuaishou_post_rows(page, max_posts=int(cfg["max_scan_posts"]))

                with self.session_factory() as session:
                    account = session.get(PublisherAccount, account_id)
                    if account is None:
                        raise ValueError(f"account_not_active:{account_id}")

                    for post_row in post_rows:
                        if int(post_row.get("comment_count") or 0) <= 0:
                            continue

                        summary.posts_scanned += 1
                        post_id = post_id_from_row(account.platform, post_row)
                        post_title = str(post_row.get("title") or "").strip()
                        job = job_by_post.get(post_id)

                        session_ctx = activate_kuaishou_post_session(page, post_row=post_row)
                        comments = fetch_kuaishou_comments_for_post(
                            page,
                            photo_id=post_id,
                            post_title=post_title,
                            account_nickname=account_nickname,
                            skip_feed_select=session_ctx.feed_active,
                        )
                        comments = merge_post_backlog(
                            session,
                            account=account,
                            post_id=post_id,
                            api_comments=comments,
                            lookback=lookback,
                        )

                        if not session_ctx.feed_active:
                            summary.activation_failures += 1
                            for comment in comments:
                                existing = (
                                    session.query(CommentInbox)
                                    .filter_by(
                                        platform=account.platform,
                                        platform_comment_id=comment.platform_comment_id,
                                    )
                                    .first()
                                )
                                if existing is not None:
                                    continue
                                self._insert_failed(
                                    session,
                                    account=account,
                                    comment=comment,
                                    post_title=post_title,
                                    job=job,
                                    error_message="work_not_found",
                                )
                                summary.errors += 1
                            prune_kuaishou_extra_pages(sess.context, page)
                            continue

                        replied_on_post = 0
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
                                account_nickname=account_nickname,
                                author_first_comments=first_comments,
                                lookback=lookback,
                                intent="inline",
                                retry_max=int(cfg["retry_max"]),
                            )
                            if not decision.process:
                                if decision.reason == "already_replied":
                                    summary.already_replied += 1
                                if decision.record_skip and existing is None:
                                    self._insert_skipped(
                                        session,
                                        account=account,
                                        comment=comment,
                                        post_title=post_title,
                                        job=job,
                                        reason=decision.reason or "skipped",
                                    )
                                    summary.skipped += 1
                                continue

                            summary.comments_seen += 1

                            if replies_this_run >= int(cfg["max_replies_per_run"]):
                                continue
                            if replied_on_post >= int(cfg["max_replies_per_post"]):
                                continue

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
                                summary.errors += 1
                                logger.warning(
                                    "Comment reply generation failed for %s: %s",
                                    comment.platform_comment_id,
                                    exc,
                                )
                                continue

                            if comment.already_replied_by_author:
                                summary.already_replied += 1
                                self._insert_skipped(
                                    session,
                                    account=account,
                                    comment=comment,
                                    post_title=post_title,
                                    job=job,
                                    reason="already_replied",
                                )
                                summary.skipped += 1
                                continue

                            result = reply_kuaishou_audience_comment_on_active_feed(
                                page,
                                session=session_ctx,
                                comment=comment,
                                reply_text=reply_text,
                            )

                            if result.success:
                                self._save_inline_outcome(
                                    session,
                                    existing=existing,
                                    account=account,
                                    comment=comment,
                                    post_title=post_title,
                                    job=job,
                                    reply_text=reply_text,
                                    success=True,
                                )
                                summary.auto_sent += 1
                                replies_this_run += 1
                                replied_on_post += 1
                            else:
                                self._save_inline_outcome(
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
                                summary.errors += 1

                            pause = int(cfg.get("pause_between_replies_sec") or 0)
                            if pause > 0:
                                time.sleep(pause)

                        prune_kuaishou_extra_pages(sess.context, page)

                    session.commit()
            finally:
                finalize_kuaishou_comment_page(sess.context, page)

        logger.info(
            "Comment reply inline kuaishou account={} posts={} seen={} sent={} skipped={} already_replied={} activation_failures={}",
            account_id,
            summary.posts_scanned,
            summary.comments_seen,
            summary.auto_sent,
            summary.skipped,
            summary.already_replied,
            summary.activation_failures,
        )
        return summary



    def scan_douyin_inline(self, account_id: str) -> ScanRunSummary:
        from services.publishing.adapters.douyin_audience_reply import (
            activate_douyin_post_session,
            douyin_author_already_replied_in_thread,
            fetch_douyin_comments_for_post,
            reply_douyin_audience_comment_on_active_feed,
            scan_douyin_post_rows,
            _navigate_comment_hub,
        )

        cfg = load_comment_reply_config()

        with self.session_factory() as session:
            account = session.get(PublisherAccount, account_id)
            if account is None or account.status != "active":
                raise ValueError(f"account_not_active:{account_id}")
            if account.platform != "douyin":
                raise ValueError(f"inline_unsupported_platform:{account.platform}")

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
            account_nickname = account.nickname
            account_platform = account.platform

        summary = ScanRunSummary(account_id=account_id, platform=account_platform)
        lookback = datetime.utcnow() - timedelta(hours=int(cfg["lookback_hours"]))
        replies_this_run = 0

        with open_adapter_browser(session_path, mode="keepalive", headless=False) as sess:
            page = sess.page
            _navigate_comment_hub(page)
            post_rows = scan_douyin_post_rows(page, max_posts=int(cfg["max_scan_posts"]))

            with self.session_factory() as session:
                account = session.get(PublisherAccount, account_id)
                if account is None:
                    raise ValueError(f"account_not_active:{account_id}")

                for post_row in post_rows:
                    if int(post_row.get("comment_count") or 0) <= 0:
                        continue

                    summary.posts_scanned += 1
                    post_id = post_id_from_row(account.platform, post_row)
                    post_title = str(post_row.get("title") or "").strip()
                    job = job_by_post.get(post_id)

                    session_ctx = activate_douyin_post_session(page, post_row=post_row)
                    comments = fetch_douyin_comments_for_post(
                        page,
                        video_id=post_id,
                        post_title=post_title,
                        account_nickname=account_nickname,
                    )
                    comments = merge_post_backlog(
                        session,
                        account=account,
                        post_id=post_id,
                        api_comments=comments,
                        lookback=lookback,
                    )

                    if not session_ctx.feed_active:
                        summary.activation_failures += 1
                        for comment in comments:
                            existing = (
                                session.query(CommentInbox)
                                .filter_by(
                                    platform=account.platform,
                                    platform_comment_id=comment.platform_comment_id,
                                )
                                .first()
                            )
                            if existing is not None:
                                continue
                            self._insert_failed(
                                session,
                                account=account,
                                comment=comment,
                                post_title=post_title,
                                job=job,
                                error_message="work_not_found",
                            )
                            summary.errors += 1
                        continue

                    replied_on_post = 0
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
                            account_nickname=account_nickname,
                            author_first_comments=first_comments,
                            lookback=lookback,
                            intent="inline",
                            retry_max=int(cfg["retry_max"]),
                        )
                        cached_reply_text = (
                            str(existing.reply_text or "").strip() if existing is not None else ""
                        ) or None

                        if not decision.process:
                            if (
                                existing is not None
                                and existing.status == "failed"
                                and cached_reply_text
                                and douyin_author_already_replied_in_thread(
                                    page,
                                    video_id=post_id,
                                    comment_id=comment.platform_comment_id,
                                    account_nickname=account_nickname,
                                    expected_reply_text=cached_reply_text,
                                )
                            ):
                                existing.status = "replied"
                                existing.replied_at = datetime.utcnow()
                                existing.error_message = None
                                session.commit()
                                summary.already_replied += 1
                                continue
                            if decision.reason == "already_replied":
                                summary.already_replied += 1
                            if decision.record_skip and existing is None:
                                self._insert_skipped(
                                    session,
                                    account=account,
                                    comment=comment,
                                    post_title=post_title,
                                    job=job,
                                    reason=decision.reason or "skipped",
                                )
                                summary.skipped += 1
                                session.commit()
                            continue

                        summary.comments_seen += 1

                        if replies_this_run >= int(cfg["max_replies_per_run"]):
                            continue
                        if replied_on_post >= int(cfg["max_replies_per_post"]):
                            continue

                        if douyin_author_already_replied_in_thread(
                            page,
                            video_id=post_id,
                            comment_id=comment.platform_comment_id,
                            account_nickname=account_nickname,
                            expected_reply_text=cached_reply_text,
                        ):
                            summary.already_replied += 1
                            if existing is None:
                                self._insert_skipped(
                                    session,
                                    account=account,
                                    comment=comment,
                                    post_title=post_title,
                                    job=job,
                                    reason="already_replied",
                                )
                                summary.skipped += 1
                                session.commit()
                            elif existing.status != "replied":
                                existing.status = "replied"
                                existing.replied_at = datetime.utcnow()
                                existing.error_message = None
                                session.commit()
                            continue

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
                            summary.errors += 1
                            logger.warning(
                                "Comment reply generation failed for %s: %s",
                                comment.platform_comment_id,
                                exc,
                            )
                            continue

                        if comment.already_replied_by_author:
                            summary.already_replied += 1
                            self._insert_skipped(
                                session,
                                account=account,
                                comment=comment,
                                post_title=post_title,
                                job=job,
                                reason="already_replied",
                            )
                            summary.skipped += 1
                            continue

                        result = reply_douyin_audience_comment_on_active_feed(
                            page,
                            session=session_ctx,
                            comment=comment,
                            reply_text=reply_text,
                            account_nickname=account_nickname,
                        )

                        if result.success:
                            self._save_inline_outcome(
                                session,
                                existing=existing,
                                account=account,
                                comment=comment,
                                post_title=post_title,
                                job=job,
                                reply_text=reply_text,
                                success=True,
                            )
                            summary.auto_sent += 1
                            replies_this_run += 1
                            replied_on_post += 1
                        else:
                            self._save_inline_outcome(
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
                            summary.errors += 1

                        pause = int(cfg.get("pause_between_replies_sec") or 0)
                        if pause > 0:
                            time.sleep(pause)

                session.commit()

        logger.info(
            "Comment reply inline douyin account={} posts={} seen={} sent={} skipped={} already_replied={} activation_failures={}",
            account_id,
            summary.posts_scanned,
            summary.comments_seen,
            summary.auto_sent,
            summary.skipped,
            summary.already_replied,
            summary.activation_failures,
        )
        return summary



    def scan_account(self, account_id: str) -> ScanRunSummary:

        cfg = load_comment_reply_config()

        with self.session_factory() as session:
            account = session.get(PublisherAccount, account_id)
            if account is None or account.status != "active":
                raise ValueError(f"account_not_active:{account_id}")
            if account.platform not in SUPPORTED_PLATFORMS:
                raise ValueError(f"unsupported_platform:{account.platform}")
            if cfg.get("effective_mode") == "inline" and account.platform == "wechat_channels":
                return self.scan_account_inline(account_id)
            if cfg.get("effective_mode") == "inline" and account.platform == "kuaishou":
                return self.scan_kuaishou_inline(account_id)
            if cfg.get("effective_mode") == "inline" and account.platform == "douyin":
                return self.scan_douyin_inline(account_id)

        mode = str(cfg.get("mode", "approve"))

        with self.session_factory() as session:

            account = session.get(PublisherAccount, account_id)

            if account is None or account.status != "active":

                raise ValueError(f"account_not_active:{account_id}")

            if account.platform not in SUPPORTED_PLATFORMS:

                raise ValueError(f"unsupported_platform:{account.platform}")



            session_path = resolve_data_path(account.session_path)

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

            match_specs_by_post: dict[str, dict[str, list[str]]] = {}

            for post_id, job in job_by_post.items():

                spec = build_feed_match_spec_from_job(session, job, post_title=str(job.title or ""))

                if spec:

                    match_specs_by_post[post_id] = spec



        summary = ScanRunSummary(account_id=account.id, platform=account.platform)

        def _resolve_feed_match_spec(post_row: dict) -> dict[str, list[str]] | None:
            from services.publishing.adapters.wechat_channels_audience_reply import normalize_wechat_export_id

            post_id = normalize_wechat_export_id(str(post_row.get("export_id") or ""))
            return match_specs_by_post.get(post_id)

        with open_adapter_browser(session_path, mode="keepalive", headless=False) as sess:

            page = sess.page
            if account.platform == "kuaishou":
                from services.publishing.adapters.kuaishou_comment import (
                    finalize_kuaishou_comment_page,
                    prepare_kuaishou_comment_page,
                )

                page = prepare_kuaishou_comment_page(sess.context, page)

            try:
                batches = scan_account_comments(

                    account.platform,

                    page,

                    account_nickname=account.nickname,

                    max_posts=int(cfg["max_scan_posts"]),

                    match_spec_resolver=_resolve_feed_match_spec if account.platform == "wechat_channels" else None,

                )
            finally:
                if account.platform == "kuaishou":
                    finalize_kuaishou_comment_page(sess.context, page)



        lookback = datetime.utcnow() - timedelta(hours=int(cfg["lookback_hours"]))

        new_pending = 0

        auto_sent = 0

        auto_queue: list[str] = []



        with self.session_factory() as session:

            account = session.get(PublisherAccount, account_id)

            for post_row, comments in batches:

                summary.posts_scanned += 1

                post_id = post_id_from_row(account.platform, post_row)

                post_title = str(post_row.get("title") or "").strip()

                job = job_by_post.get(post_id)

                post_context = build_wechat_inbox_post_context(
                    post_row=post_row,
                    job=job,
                    session=session,
                )
                post_context_json = dumps_post_context(post_context)

                for comment in comments:

                    summary.comments_seen += 1

                    existing = (

                        session.query(CommentInbox)

                        .filter_by(

                            platform=account.platform,

                            platform_comment_id=comment.platform_comment_id,

                        )

                        .first()

                    )

                    if existing is not None:

                        continue

                    if comment.commented_at and comment.commented_at < lookback:

                        summary.skipped += 1

                        self._insert_skipped(

                            session,

                            account=account,

                            comment=comment,

                            post_title=post_title,

                            job=job,

                            reason="too_old",

                        )

                        continue

                    skip_reason = should_skip_comment(

                        comment,

                        account_nickname=account.nickname,

                        author_first_comments=first_comments,

                    )

                    if skip_reason:

                        summary.skipped += 1

                        self._insert_skipped(

                            session,

                            account=account,

                            comment=comment,

                            post_title=post_title,

                            job=job,

                            reason=skip_reason,

                        )

                        continue

                    if (new_pending + auto_sent) >= int(cfg["max_new_replies_per_run"]):

                        continue

                    session.commit()

                    try:

                        reply_text = generate_comment_reply(

                            post_title=post_title or (job.title if job else ""),

                            post_description=job.description if job else None,

                            audience_comment=comment.content,

                            audience_name=comment.author_name,

                            min_length=int(cfg["reply_min_length"]),

                            max_length=int(cfg["reply_max_length"]),

                        )

                    except Exception as exc:

                        summary.errors += 1

                        logger.warning(

                            "Comment reply generation failed for %s: %s",

                            comment.platform_comment_id,

                            exc,

                    )

                        continue

                    row = CommentInbox(

                        account_id=account.id,

                        platform=account.platform,

                        platform_post_id=post_id or comment.platform_post_id,

                        platform_comment_id=comment.platform_comment_id,

                        publish_job_id=job.id if job else None,

                        post_title=post_title or (job.title if job else None),

                        author_name=comment.author_name,

                        content=comment.content,

                        commented_at=comment.commented_at,

                        status="pending_approval",

                        reply_text=reply_text,

                        post_context_json=post_context_json,

                    )

                    session.add(row)

                    session.flush()

                    if mode == "auto" and auto_sent < int(cfg["max_auto_replies_per_run"]):

                        auto_queue.append(row.id)

                        auto_sent += 1

                    else:

                        new_pending += 1

            session.commit()



        if auto_queue:

            for inbox_id in auto_queue:

                result = self._send_inbox_item(inbox_id)

                if result.get("success"):

                    summary.auto_sent += 1

                else:

                    summary.errors += 1



        summary.new_pending = new_pending

        logger.info(

            "Comment reply scan account={} posts={} seen={} pending={} auto={} skipped={}",

            account_id,

            summary.posts_scanned,

            summary.comments_seen,

            summary.new_pending,

            summary.auto_sent,

            summary.skipped,

        )

        return summary



    def retry_failed_replies(self) -> dict:

        cfg = load_comment_reply_config()

        retried = 0

        failed = 0

        with self.session_factory() as session:

            rows = (

                session.query(CommentInbox)

                .filter(

                    CommentInbox.status == "failed",

                    CommentInbox.retry_count < int(cfg["retry_max"]),

                )

                .order_by(CommentInbox.updated_at.asc())

                .limit(int(cfg["retry_batch_size"]))

                .all()

            )

            inbox_ids = [row.id for row in rows]



        for inbox_id in inbox_ids:

            result = self._send_inbox_item(inbox_id)

            if result.get("success"):

                retried += 1

            else:

                failed += 1



        logger.info("Comment reply retry done retried={} failed={}", retried, failed)

        return {"success": True, "retried": retried, "failed": failed, "total": len(inbox_ids)}



    def approve_inbox_item(self, inbox_id: str, *, reply_text: str | None = None) -> dict:

        cfg = load_comment_reply_config()

        with self.session_factory() as session:

            row = session.get(CommentInbox, inbox_id)

            if row is None:

                return {"success": False, "error": "inbox_not_found"}

            if row.status not in {"pending_approval", "failed"}:

                return {"success": False, "error": f"invalid_status:{row.status}"}

            final_reply = validate_reply_text(

                reply_text or row.reply_text or "",

                min_length=int(cfg["reply_min_length"]),

                max_length=int(cfg["reply_max_length"]),

            )

            row.reply_text = final_reply

            session.commit()

        return self._send_inbox_item(inbox_id, reply_text=final_reply)



    def _send_inbox_item(self, inbox_id: str, *, reply_text: str | None = None) -> dict:

        with self.session_factory() as session:

            row = session.get(CommentInbox, inbox_id)

            if row is None:

                return {"success": False, "error": "inbox_not_found"}

            if row.status not in {"pending_approval", "failed"}:

                return {"success": False, "error": f"invalid_status:{row.status}"}

            account = session.get(PublisherAccount, row.account_id)

            if account is None:

                return {"success": False, "error": "account_not_found"}

            final_reply = (reply_text or row.reply_text or "").strip()

            if not final_reply:

                return {"success": False, "error": "empty_reply_text"}



            session_path = resolve_data_path(account.session_path)

            post_title = row.post_title or ""

            job = None

            if row.publish_job_id:

                job = session.get(PublishJob, row.publish_job_id)

            if job is None:

                job = (

                    session.query(PublishJob)

                    .filter(PublishJob.platform_post_id == row.platform_post_id)

                    .order_by(PublishJob.created_at.desc())

                    .first()

                )

            feed_match_spec = resolve_wechat_feed_match_spec(
                session,
                job,
                row,
                post_title,
            )
            ctx = parse_post_context(row.post_context_json)
            post_description = str(ctx.get("description") or (job.description if job else "") or "")

            with open_adapter_browser(session_path, mode="keepalive", headless=False) as sess:
                page = sess.page
                if account.platform == "kuaishou":
                    from services.publishing.adapters.kuaishou_comment import (
                        finalize_kuaishou_comment_page,
                        prepare_kuaishou_comment_page,
                    )

                    page = prepare_kuaishou_comment_page(sess.context, page)

                platform_comment = InboundComment(
                    platform_post_id=row.platform_post_id,
                    platform_comment_id=row.platform_comment_id,
                    author_name=row.author_name or "",
                    content=row.content,
                    commented_at=row.commented_at,
                )
                if account.platform == "douyin":
                    fetched = fetch_douyin_comments_for_post(
                        sess.page,
                        video_id=row.platform_post_id,
                        post_title=post_title,
                        account_nickname=account.nickname,
                    )
                    for item in fetched:
                        if item.platform_comment_id == row.platform_comment_id:
                            platform_comment = item
                            break
                elif account.platform == "wechat_channels":
                    fetched = fetch_wechat_comments_for_post(
                        sess.page,
                        export_id=row.platform_post_id,
                        post_title=post_title,
                        account_nickname=account.nickname,
                    )
                    for item in fetched:
                        if item.platform_comment_id == row.platform_comment_id:
                            platform_comment = item
                            break

                decision = should_process_comment(
                    platform_comment,
                    existing_row=row,
                    account_nickname=account.nickname,
                    author_first_comments=set(),
                    intent="retry",
                )
                if not decision.process:
                    if decision.update_status:
                        row.status = decision.update_status
                        row.skip_reason = decision.reason
                        row.error_message = None
                    session.commit()
                    if account.platform == "kuaishou":
                        finalize_kuaishou_comment_page(sess.context, page)
                    return {
                        "success": False,
                        "status": row.status,
                        "error": decision.reason,
                    }

                try:
                    result = reply_audience_comment(

                        account.platform,

                        page,

                        platform_post_id=row.platform_post_id,

                        post_title=post_title,

                        platform_comment_id=row.platform_comment_id,

                        comment_content=row.content,

                        reply_text=final_reply,

                        post_description=post_description or None,

                        main_line1=str(ctx.get("main_line1") or ""),

                        main_line2=str(ctx.get("main_line2") or ""),

                        sub_title=str(ctx.get("sub_title") or ""),

                        sub_title2=str(ctx.get("sub_title2") or ""),

                        feed_match_spec=feed_match_spec,

                        account_nickname=account.nickname,

                    )
                finally:
                    if account.platform == "kuaishou":
                        finalize_kuaishou_comment_page(sess.context, page)



            row = session.get(CommentInbox, inbox_id)

            if row is None:

                return {"success": False, "error": "inbox_not_found"}

            if result.success:

                row.status = "replied"

                row.replied_at = datetime.utcnow()

                row.error_message = None

            else:

                row.status = "failed"

                row.retry_count = (row.retry_count or 0) + 1

                row.error_message = result.error_message

            session.commit()

            return {

                "success": result.success,

                "status": row.status,

                "error": result.error_message,

            }



    def reject_inbox_item(self, inbox_id: str, *, reason: str = "rejected") -> dict:

        with self.session_factory() as session:

            row = session.get(CommentInbox, inbox_id)

            if row is None:

                return {"success": False, "error": "inbox_not_found"}

            if row.status != "pending_approval":

                return {"success": False, "error": f"invalid_status:{row.status}"}

            row.status = "skipped"

            row.skip_reason = reason

            session.commit()

            return {"success": True, "status": row.status}



    def regenerate_pending_replies(self) -> dict:

        """Re-generate reply_text for all pending_approval inbox rows."""

        cfg = load_comment_reply_config()

        regenerated = 0

        errors = 0

        with self.session_factory() as session:

            rows = (

                session.query(CommentInbox)

                .filter(CommentInbox.status == "pending_approval")

                .order_by(CommentInbox.created_at.asc())

                .all()

            )

            job_ids = {row.publish_job_id for row in rows if row.publish_job_id}

            jobs = {

                item.id: item

                for item in session.query(PublishJob).filter(PublishJob.id.in_(job_ids)).all()

            } if job_ids else {}

            for row in rows:

                job = jobs.get(row.publish_job_id) if row.publish_job_id else None

                session.commit()

                try:

                    row.reply_text = generate_comment_reply(

                        post_title=row.post_title or (job.title if job else ""),

                        post_description=job.description if job else None,

                        audience_comment=row.content,

                        audience_name=row.author_name,

                        min_length=int(cfg["reply_min_length"]),

                        max_length=int(cfg["reply_max_length"]),

                    )

                    regenerated += 1

                except Exception as exc:

                    errors += 1

                    logger.warning(

                        "Comment reply regenerate failed for %s: %s",

                        row.id,

                        exc,

                    )

            session.commit()

        logger.info(

            "Comment reply regenerate done total={} ok={} errors={}",

            len(rows),

            regenerated,

            errors,

        )

        return {

            "success": True,

            "total": len(rows),

            "regenerated": regenerated,

            "errors": errors,

        }



    @staticmethod

    def _save_inline_outcome(
        session: Session,
        *,
        existing,
        account,
        comment,
        post_title,
        job,
        reply_text: str,
        success: bool,
        error_message: str | None = None,
        post_context_json: str | None = None,
    ) -> None:
        if existing is not None:
            if success:
                existing.status = "replied"
                existing.replied_at = datetime.utcnow()
                existing.error_message = None
                existing.reply_text = reply_text
                if post_context_json and not existing.post_context_json:
                    existing.post_context_json = post_context_json
            else:
                existing.status = "failed"
                existing.retry_count = (existing.retry_count or 0) + 1
                existing.error_message = error_message
                if reply_text:
                    existing.reply_text = reply_text
            session.commit()
            return

        if success:
            CommentReplyOrchestrator._insert_replied(
                session,
                account=account,
                comment=comment,
                post_title=post_title,
                job=job,
                reply_text=reply_text,
                post_context_json=post_context_json,
            )
            session.commit()
            return

        CommentReplyOrchestrator._insert_failed(
            session,
            account=account,
            comment=comment,
            post_title=post_title,
            job=job,
            error_message=error_message or "send_failed",
            reply_text=reply_text,
            post_context_json=post_context_json,
        )
        session.commit()



    @staticmethod

    def _insert_skipped(session: Session, *, account, comment, post_title, job, reason: str) -> None:

        row = CommentInbox(

            account_id=account.id,

            platform=account.platform,

            platform_post_id=comment.platform_post_id,

            platform_comment_id=comment.platform_comment_id,

            publish_job_id=job.id if job else None,

            post_title=post_title or (job.title if job else None),

            author_name=comment.author_name,

            content=comment.content,

            commented_at=comment.commented_at,

            status="skipped",

            skip_reason=reason,

        )

        session.add(row)



    @staticmethod

    def _insert_replied(session: Session, *, account, comment, post_title, job, reply_text: str, post_context_json: str | None = None) -> None:

        row = CommentInbox(

            account_id=account.id,

            platform=account.platform,

            platform_post_id=comment.platform_post_id,

            platform_comment_id=comment.platform_comment_id,

            publish_job_id=job.id if job else None,

            post_title=post_title or (job.title if job else None),

            author_name=comment.author_name,

            content=comment.content,

            commented_at=comment.commented_at,

            status="replied",

            reply_text=reply_text,

            replied_at=datetime.utcnow(),

            post_context_json=post_context_json,

        )

        session.add(row)



    @staticmethod

    def _insert_failed(session: Session, *, account, comment, post_title, job, error_message: str, reply_text: str | None = None, post_context_json: str | None = None) -> None:

        row = CommentInbox(

            account_id=account.id,

            platform=account.platform,

            platform_post_id=comment.platform_post_id,

            platform_comment_id=comment.platform_comment_id,

            publish_job_id=job.id if job else None,

            post_title=post_title or (job.title if job else None),

            author_name=comment.author_name,

            content=comment.content,

            commented_at=comment.commented_at,

            status="failed",

            reply_text=reply_text,

            error_message=error_message,

            retry_count=1,

            post_context_json=post_context_json,

        )

        session.add(row)


