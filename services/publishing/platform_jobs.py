"""Adjust publish platforms for queued jobs."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from services.publishing.auto_publish import (
    SOURCE_TYPE,
    _build_fields_for_platform,
    _parse_video_draft,
    _resolve_media_paths,
)
from services.publishing.compliance import validate_publish_payload
from services.publishing.metadata_bridge import draft_from_video_draft
from services.publishing.platform_capabilities import can_video_publish
from services.publishing.registry import PlatformNotFoundError, get_platform_config, list_platforms
from src.db.models.ingestion import IngestedArticle
from src.db.models.publishing import PublishJob, PublisherAccount

_ACTIVE_JOB_STATUSES = ("pending", "uploading")


def eligible_video_platform_ids() -> list[str]:
    ids: list[str] = []
    for cfg in list_platforms():
        platform_id = cfg.get("id")
        if not platform_id or not cfg.get("enabled", False):
            continue
        if can_video_publish(platform_id):
            ids.append(platform_id)
    return ids


def pick_account_for_platform(session: Session, platform_id: str) -> PublisherAccount | None:
    rows = (
        session.query(PublisherAccount)
        .filter(PublisherAccount.platform == platform_id)
        .order_by(PublisherAccount.last_login_at.desc().nullslast())
        .all()
    )
    if not rows:
        return None
    active = [row for row in rows if row.status == "active"]
    return active[0] if active else rows[0]


def _normalize_platforms(platforms: list[str]) -> list[str]:
    eligible = set(eligible_video_platform_ids())
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in platforms:
        platform_id = str(raw or "").strip()
        if not platform_id or platform_id in seen:
            continue
        if platform_id not in eligible:
            raise ValueError(f"平台不可用或未开放视频发布: {platform_id}")
        seen.add(platform_id)
        normalized.append(platform_id)
    if not normalized:
        raise ValueError("请至少选择一个平台")
    return normalized


def _jobs_in_scope(session: Session, job: PublishJob) -> list[PublishJob]:
    if job.source_type == SOURCE_TYPE and job.source_id:
        return (
            session.query(PublishJob)
            .filter(
                PublishJob.source_type == SOURCE_TYPE,
                PublishJob.source_id == job.source_id,
                PublishJob.status.in_(_ACTIVE_JOB_STATUSES),
            )
            .all()
        )
    if job.status in _ACTIVE_JOB_STATUSES:
        return [job]
    return []


def _account_map(session: Session, jobs: list[PublishJob]) -> dict[str, PublisherAccount]:
    account_ids = [job.account_id for job in jobs]
    if not account_ids:
        return {}
    rows = session.query(PublisherAccount).filter(PublisherAccount.id.in_(account_ids)).all()
    return {row.id: row for row in rows}


def _create_job_for_platform(
    session: Session,
    *,
    account: PublisherAccount,
    article: IngestedArticle | None,
    template: PublishJob,
    scheduled_at: datetime | None,
) -> PublishJob:
    if article is not None:
        fields = _build_fields_for_platform(article, account.platform)
        video_path, cover_path = _resolve_media_paths(article)
        draft = draft_from_video_draft(_parse_video_draft(article))
        first_comment_text = (draft.first_comment or "").strip() or None
    else:
        fields = {
            "title": template.title,
            "description": template.description,
            "tags": json.loads(template.tags_json or "[]"),
        }
        video_path = template.video_path
        cover_path = template.cover_path
        first_comment_text = template.first_comment_text

    title = (fields.get("title") or "").strip()
    description = (fields.get("description") or "").strip() or None
    tags = fields.get("tags") or []
    compliance = validate_publish_payload(title, description, tags)
    if not compliance.ok:
        raise ValueError(f"平台 {account.platform} 的发布文案未通过合规检查")

    job_cover_path = cover_path
    if account.platform == "douyin":
        job_cover_path = None

    job = PublishJob(
        account_id=account.id,
        video_path=video_path,
        title=title,
        description=description,
        tags_json=json.dumps(tags, ensure_ascii=False),
        cover_path=job_cover_path,
        source_type=template.source_type,
        source_id=template.source_id,
        status="pending",
        scheduled_at=scheduled_at,
        first_comment_text=first_comment_text,
        comment_status="none",
    )
    session.add(job)
    session.flush()
    return job


def update_job_platforms(session: Session, job_id: str, platforms: list[str]) -> dict[str, Any]:
    job = session.get(PublishJob, job_id)
    if job is None:
        raise ValueError("任务不存在")

    requested = _normalize_platforms(platforms)
    jobs = _jobs_in_scope(session, job)
    if not jobs:
        raise ValueError("仅待发布或上传中的任务可修改平台")

    if not (job.source_type == SOURCE_TYPE and job.source_id):
        if len(requested) != 1:
            raise ValueError("手动任务只能选择一个平台")
        new_platform = requested[0]
        account = pick_account_for_platform(session, new_platform)
        if account is None:
            raise ValueError(f"平台 {new_platform} 暂无绑定账号，请先在发布中心登录")
        if job.status == "uploading":
            raise ValueError("上传中的任务无法修改平台")

        article = (
            session.get(IngestedArticle, job.source_id)
            if job.source_type == SOURCE_TYPE and job.source_id
            else None
        )
        if article is not None:
            fields = _build_fields_for_platform(article, new_platform)
            job.title = (fields.get("title") or job.title).strip()
            job.description = (fields.get("description") or "").strip() or None
            job.tags_json = json.dumps(fields.get("tags") or [], ensure_ascii=False)
            if new_platform == "douyin":
                job.cover_path = None
        job.account_id = account.id
        return {
            "updated": True,
            "platform": new_platform,
            "account_id": account.id,
        }

    accounts = _account_map(session, jobs)
    current_by_platform: dict[str, PublishJob] = {}
    for active_job in jobs:
        account = accounts.get(active_job.account_id)
        if account:
            current_by_platform[account.platform] = active_job

    target_set = set(requested)
    cancelled: list[str] = []
    created: list[dict[str, str]] = []
    kept = sorted(target_set & set(current_by_platform.keys()))

    for platform, active_job in current_by_platform.items():
        if platform in target_set:
            continue
        if active_job.status == "uploading":
            display = platform
            try:
                display = get_platform_config(platform).get("display_name", platform)
            except PlatformNotFoundError:
                pass
            raise ValueError(f"{display} 正在上传，无法移除")
        active_job.status = "cancelled"
        active_job.finished_at = datetime.utcnow()
        cancelled.append(platform)

    representative = jobs[0]
    scheduled_at = representative.scheduled_at
    article = session.get(IngestedArticle, job.source_id) if job.source_id else None

    for platform in requested:
        if platform in current_by_platform:
            continue
        account = pick_account_for_platform(session, platform)
        if account is None:
            try:
                display = get_platform_config(platform).get("display_name", platform)
            except PlatformNotFoundError:
                display = platform
            raise ValueError(f"{display} 暂无绑定账号，请先在发布中心登录")
        new_job = _create_job_for_platform(
            session,
            account=account,
            article=article,
            template=representative,
            scheduled_at=scheduled_at,
        )
        created.append({"job_id": new_job.id, "platform": platform, "account_id": account.id})

    return {"cancelled": cancelled, "created": created, "kept": kept}
