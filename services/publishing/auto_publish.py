"""Enqueue publish jobs after ingested video render succeeds."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from services.ingestion.article_scorer import load_scoring_config
from services.publishing.compliance import validate_publish_payload
from services.publishing.metadata_bridge import draft_from_video_draft, draft_to_publish_fields
from services.publishing.path_guard import PathGuardError, resolve_cover_path, resolve_video_path, to_relative_posix
from services.publishing.platform_capabilities import can_video_publish
from services.publishing.registry import PlatformNotFoundError, get_platform_config
from src.db.models.ingestion import IngestedArticle
from src.db.models.publishing import PublishJob, PublisherAccount

SOURCE_TYPE = "ingestion"
_ACTIVE_JOB_STATUSES = ("pending", "uploading", "published")


def load_auto_publish_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    active = cfg or load_scoring_config()
    auto = active.get("post_score_automation") or {}
    publish_cfg = auto.get("auto_publish") or {}
    return {
        "enabled": bool(publish_cfg.get("enabled", True)),
        "skip_if_exists": bool(publish_cfg.get("skip_if_exists", True)),
    }


def _parse_video_draft(article: IngestedArticle) -> dict[str, Any]:
    if article.video_draft_json:
        try:
            data = json.loads(article.video_draft_json)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"main_line1": (article.title or "未命名").strip()}


def _select_accounts_for_auto_publish(session: Session) -> list[PublisherAccount]:
    rows = (
        session.query(PublisherAccount)
        .filter(PublisherAccount.status == "active")
        .order_by(PublisherAccount.last_login_at.desc().nullslast())
        .all()
    )
    selected: list[PublisherAccount] = []
    seen_platforms: set[str] = set()
    for account in rows:
        if account.platform in seen_platforms:
            continue
        try:
            cfg = get_platform_config(account.platform)
        except PlatformNotFoundError:
            continue
        if not cfg.get("enabled", False):
            continue
        if not can_video_publish(account.platform):
            continue
        seen_platforms.add(account.platform)
        selected.append(account)
    return selected


def _has_existing_job(
    session: Session,
    *,
    account_id: str,
    source_type: str,
    source_id: str,
) -> bool:
    row = (
        session.query(PublishJob)
        .filter(
            PublishJob.account_id == account_id,
            PublishJob.source_type == source_type,
            PublishJob.source_id == source_id,
            PublishJob.status.in_(_ACTIVE_JOB_STATUSES),
        )
        .first()
    )
    return row is not None


def _build_fields_for_platform(article: IngestedArticle, platform_id: str) -> dict[str, Any]:
    cfg = get_platform_config(platform_id)
    limits = cfg.get("limits") or {}
    draft = draft_from_video_draft(_parse_video_draft(article))
    return draft_to_publish_fields(
        draft,
        max_title_length=int(limits.get("max_title_length", 30)),
        max_tags=int(limits.get("max_tags", 10)),
        platform_id=platform_id,
    )


def _resolve_media_paths(article: IngestedArticle) -> tuple[str, str | None]:
    video = resolve_video_path(article.generated_video_path or "")
    cover_rel: str | None = None
    if article.generated_cover_path:
        cover = resolve_cover_path(article.generated_cover_path)
        cover_rel = to_relative_posix(cover) if cover else None
    return to_relative_posix(video), cover_rel


def maybe_enqueue_auto_publish_jobs(
    session: Session,
    article: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one pending publish job per active platform account. Never raises."""
    cfg = load_auto_publish_config(config)
    if not cfg.get("enabled", True):
        return {"skipped": True, "reason": "disabled"}

    if not article.generated_video_path:
        return {"skipped": True, "reason": "no_video"}

    try:
        video_path, cover_path = _resolve_media_paths(article)
    except PathGuardError as exc:
        logger.warning("auto_publish skipped article=%s: %s", article.id, exc)
        return {"skipped": True, "reason": "invalid_media_path", "error": str(exc)}

    accounts = _select_accounts_for_auto_publish(session)
    if not accounts:
        return {"skipped": True, "reason": "no_active_accounts"}

    created: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for account in accounts:
        if cfg.get("skip_if_exists", True) and _has_existing_job(
            session,
            account_id=account.id,
            source_type=SOURCE_TYPE,
            source_id=article.id,
        ):
            skipped.append(
                {
                    "account_id": account.id,
                    "platform": account.platform,
                    "reason": "already_queued",
                }
            )
            continue

        try:
            fields = _build_fields_for_platform(article, account.platform)
        except PlatformNotFoundError as exc:
            skipped.append(
                {"account_id": account.id, "platform": account.platform, "reason": str(exc)}
            )
            continue

        title = (fields.get("title") or "").strip()
        description = (fields.get("description") or "").strip() or None
        tags = fields.get("tags") or []
        compliance = validate_publish_payload(title, description, tags)
        if not compliance.ok:
            skipped.append(
                {
                    "account_id": account.id,
                    "platform": account.platform,
                    "reason": "compliance_violation",
                }
            )
            continue

        job = PublishJob(
            account_id=account.id,
            video_path=video_path,
            title=title,
            description=description,
            tags_json=json.dumps(tags, ensure_ascii=False),
            cover_path=cover_path,
            source_type=SOURCE_TYPE,
            source_id=article.id,
            status="pending",
        )
        session.add(job)
        session.flush()
        created.append(
            {
                "job_id": job.id,
                "account_id": account.id,
                "platform": account.platform,
            }
        )
        logger.info(
            "auto_publish enqueued job=%s article=%s platform=%s",
            job.id,
            article.id,
            account.platform,
        )

    if created:
        return {"enqueued": True, "jobs": created, "skipped": skipped}
    return {"skipped": True, "reason": "nothing_created", "details": skipped}
