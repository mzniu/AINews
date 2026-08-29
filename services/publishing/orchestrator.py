"""Publish job orchestration."""
from __future__ import annotations

import json
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import sessionmaker

from services.publishing.adapters.base import PublishPayload, PublishResult
from services.publishing.first_comment import (
    apply_comment_outcome,
    apply_comment_retry_outcome,
    can_retry_comment,
    should_post_first_comment,
)
from services.publishing.first_comment_settings import get_first_comment_settings
from services.publishing.first_comment_timing import get_comment_timing, is_first_comment_deferred
from services.publishing.job_logging import publish_job_scope, record_job_log
from services.publishing.metrics.post_id import is_synthetic_platform_post_id
from services.publishing.path_guard import resolve_cover_path, resolve_video_path
from services.publishing.registry import get_adapter
from src.db.models.publishing import PublishJob, PublisherAccount
from src.utils.config import Config

_SESSION_EXPIRED_MARKERS = ("会话已过期", "请重新扫码", "重新登录")


class PublishOrchestrator:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def publish_job(self, job_id: str) -> None:
        with self.session_factory() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return
            account = session.get(PublisherAccount, job.account_id)
            if account is None:
                job.status = "failed"
                job.error_message = "账号不存在"
                job.finished_at = datetime.utcnow()
                session.commit()
                return
            if account.status != "active":
                job.status = "failed"
                job.error_message = "账号会话已失效，请到发布中心重新扫码登录"
                job.finished_at = datetime.utcnow()
                session.commit()
                record_job_log(
                    self.session_factory,
                    job_id,
                    job.error_message,
                    level="error",
                )
                return
            platform = account.platform
            session_path = account.session_path
            video_path_raw = job.video_path
            cover_path_raw = job.cover_path
            title = job.title
            description = job.description
            tags = json.loads(job.tags_json or "[]")
            first_comment_text = job.first_comment_text
            comment_status = job.comment_status

        video = resolve_video_path(video_path_raw)
        cover = resolve_cover_path(cover_path_raw)
        fc_settings = get_first_comment_settings()
        comment_delay_sec, comment_wait_max_sec, _ = get_comment_timing(platform)
        should_comment = should_post_first_comment(
            first_comment_text=first_comment_text,
            comment_status=comment_status,
            platform_id=platform,
            enabled=fc_settings.get("enabled", False),
        )
        deferred_comment = should_comment and is_first_comment_deferred(platform)
        first_comment = first_comment_text if should_comment and not deferred_comment else None
        payload = PublishPayload(
            video_path=video,
            title=title,
            description=description,
            tags=tags,
            cover_path=cover,
            first_comment=first_comment,
        )
        adapter = get_adapter(platform)
        session_file = Config.ROOT_DIR / session_path

        with publish_job_scope(self.session_factory, job_id):
            record_job_log(
                self.session_factory,
                job_id,
                f"开始发布任务（平台: {platform}，标题: {title or '未命名'}）",
            )
            result = adapter.publish_video(session_file, payload)

        deferred_comment_result = None
        if result.success and deferred_comment:
            record_job_log(self.session_factory, job_id, "发布完成，开始独立会话首评")
            deferred_comment_result = adapter.post_first_comment(
                session_file,
                post_id=result.platform_post_id,
                post_url=result.platform_post_url,
                title=title,
                text=(first_comment_text or "").strip(),
                delay_sec=comment_delay_sec,
                wait_max_sec=comment_wait_max_sec,
            )

        with self.session_factory() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return
            if result.success:
                job.status = "published"
                job.platform_post_id = result.platform_post_id
                job.platform_post_url = result.platform_post_url
                if result.platform_post_id and not is_synthetic_platform_post_id(result.platform_post_id):
                    job.metrics_match_status = "matched"
                else:
                    job.metrics_match_status = "pending"
                job.published_at = datetime.utcnow()
                job.finished_at = datetime.utcnow()
                job.error_message = None
                if deferred_comment_result is not None:
                    result = PublishResult(
                        success=True,
                        platform_post_id=result.platform_post_id,
                        platform_post_url=result.platform_post_url,
                        comment_result=deferred_comment_result,
                    )
                apply_comment_outcome(
                    job,
                    result,
                    platform_id=platform,
                    enabled=fc_settings.get("enabled", False),
                )
                acc = session.get(PublisherAccount, job.account_id)
                if acc:
                    acc.last_publish_at = datetime.utcnow()
                log_message = (
                    "素材已就绪，请在浏览器中手动点击发表"
                    if result.manual_publish_pending
                    else "发布成功"
                )
                record_job_log(self.session_factory, job_id, log_message)
            else:
                job.status = "failed"
                job.finished_at = datetime.utcnow()
                job.error_message = result.error_message or "发布失败"
                acc = session.get(PublisherAccount, job.account_id)
                if acc and result.error_message and any(
                    marker in result.error_message for marker in _SESSION_EXPIRED_MARKERS
                ):
                    acc.status = "expired"
                    job.error_message = (
                        f"{result.error_message}（已标记账号为过期，请到发布中心重新登录）"
                    )
                record_job_log(
                    self.session_factory,
                    job_id,
                    job.error_message,
                    level="error",
                )
            session.commit()
        if not result.success:
            logger.error(f"Publish job {job_id} failed: {result.error_message}")

    def retry_comment_job(self, job_id: str, *, force: bool = False) -> dict[str, object]:
        with self.session_factory() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return {"success": False, "error": "job_not_found"}
            account = session.get(PublisherAccount, job.account_id)
            if account is None:
                return {"success": False, "error": "account_not_found"}
            if account.status != "active":
                return {"success": False, "error": "account_inactive"}
            platform = account.platform
            session_path = account.session_path
            first_comment_text = job.first_comment_text
            post_id = job.platform_post_id
            post_url = job.platform_post_url
            title = job.title
            comment_status = job.comment_status
            comment_retry_count = job.comment_retry_count or 0
            job_status = job.status

        fc_settings = get_first_comment_settings()
        comment_delay_sec, comment_wait_max_sec, _ = get_comment_timing(platform)
        retry_max = int(fc_settings.get("retry_max", 3))
        probe_job = PublishJob(
            id=job_id,
            account_id=account.id,
            video_path="",
            title=title or "",
            status=job_status,
            first_comment_text=first_comment_text,
            comment_status=comment_status,
            comment_retry_count=comment_retry_count,
        )
        ok, reason = can_retry_comment(
            probe_job,
            platform_id=platform,
            retry_max=retry_max,
            force=force,
        )
        if not ok:
            return {"success": False, "error": reason}

        adapter = get_adapter(platform)
        session_file = Config.ROOT_DIR / session_path

        with publish_job_scope(self.session_factory, job_id):
            record_job_log(self.session_factory, job_id, "开始重试首评")
            comment_result = adapter.post_first_comment(
                session_file,
                post_id=post_id,
                post_url=post_url,
                title=title,
                text=(first_comment_text or "").strip(),
                delay_sec=comment_delay_sec,
                wait_max_sec=comment_wait_max_sec,
            )

        with self.session_factory() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return {"success": False, "error": "job_not_found"}
            apply_comment_retry_outcome(job, comment_result)
            session.commit()
            return {
                "success": comment_result.success,
                "comment_status": job.comment_status,
                "comment_retry_count": job.comment_retry_count,
                "error": job.comment_error_message,
            }
