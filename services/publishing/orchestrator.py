"""Publish job orchestration."""
from __future__ import annotations

import json
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import sessionmaker

from services.publishing.adapters.base import PublishPayload
from services.publishing.job_logging import publish_job_scope, record_job_log
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

        video = resolve_video_path(video_path_raw)
        cover = resolve_cover_path(cover_path_raw)
        payload = PublishPayload(
            video_path=video,
            title=title,
            description=description,
            tags=tags,
            cover_path=cover,
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

        with self.session_factory() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return
            if result.success:
                job.status = "published"
                job.platform_post_id = result.platform_post_id
                job.published_at = datetime.utcnow()
                job.finished_at = datetime.utcnow()
                job.error_message = None
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
