"""Enqueue publish jobs after ingested video render succeeds."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from services.ingestion.article_scorer import VALID_GRADES, grade_meets_minimum, load_scoring_config
from services.ingestion.story_primary import check_story_media_pipeline_gate
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
        "min_grade": str(publish_cfg.get("min_grade", "S")).upper(),
    }


def _parse_video_draft(article: IngestedArticle) -> dict[str, Any]:
    if article.video_draft_json:
        try:
            data = json.loads(article.video_draft_json)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    title = (article.title or "未命名").strip()
    return {"main_line1": title, "short_title": title}


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


class PublishPayloadError(ValueError):
    """A candidate cannot safely be converted into a publish job."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def create_ingestion_publish_job(
    session: Session,
    *,
    article: IngestedArticle,
    account: PublisherAccount,
    scheduled_at,
    media_paths: tuple[str, str | None] | None = None,
    draft=None,
) -> PublishJob:
    """Build and flush one ingestion-backed job after all validation passes."""
    video_path, cover_path = media_paths or _resolve_media_paths(article)
    active_draft = draft or draft_from_video_draft(_parse_video_draft(article))
    fields = _build_fields_for_platform(article, account.platform)
    title = (fields.get("title") or "").strip()
    description = (fields.get("description") or "").strip() or None
    tags = fields.get("tags") or []
    compliance = validate_publish_payload(title, description, tags)
    if not compliance.ok:
        raise PublishPayloadError("compliance_violation")

    job = PublishJob(
        account_id=account.id,
        video_path=video_path,
        title=title,
        description=description,
        tags_json=json.dumps(tags, ensure_ascii=False),
        cover_path=None if account.platform == "douyin" else cover_path,
        source_type=SOURCE_TYPE,
        source_id=article.id,
        status="pending",
        scheduled_at=scheduled_at,
        first_comment_text=(active_draft.first_comment or "").strip() or None,
        comment_status="none",
    )
    session.add(job)
    session.flush()
    return job


def maybe_enqueue_auto_publish_jobs(
    session: Session,
    article: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one pending publish job per active platform account. Never raises."""
    active_config = config or load_scoring_config()
    if bool(active_config.get("publish_policy", {}).get("enabled", False)):
        from services.publishing.candidate_queue import evaluate_article_candidates
        from services.publishing.rollout_guard import platform_kill_switch_active

        result = evaluate_article_candidates(session, article, active_config)
        policy = active_config.get("publish_policy") or {}
        killed = [
            platform
            for platform, platform_config in (policy.get("platforms") or {}).items()
            if isinstance(platform_config, dict)
            and platform_kill_switch_active(platform_config)
        ]
        if killed:
            legacy = _enqueue_legacy_jobs(
                session,
                article,
                config=active_config,
                platforms=set(killed),
            )
            return {**result, "legacy_fallback": legacy}
        return result

    return _enqueue_legacy_jobs(session, article, config=active_config)


def _enqueue_legacy_jobs(
    session: Session,
    article: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
    platforms: set[str] | None = None,
) -> dict[str, Any]:
    cfg = load_auto_publish_config(config)
    if not cfg.get("enabled", True):
        return {"skipped": True, "reason": "disabled"}

    if not article.generated_video_path:
        return {"skipped": True, "reason": "no_video"}

    min_grade = str(cfg.get("min_grade", "S")).upper()
    article_grade = str(article.score_grade or "").upper()
    if not article_grade:
        return {"skipped": True, "reason": "no_score", "min_grade": min_grade}
    if not grade_meets_minimum(article_grade, min_grade):
        return {
            "skipped": True,
            "reason": "grade_below_threshold",
            "article_grade": article_grade,
            "min_grade": min_grade,
        }

    gate = check_story_media_pipeline_gate(session, article, config=config)
    if gate:
        return gate

    try:
        video_path, cover_path = _resolve_media_paths(article)
    except PathGuardError as exc:
        logger.warning("auto_publish skipped article=%s: %s", article.id, exc)
        return {"skipped": True, "reason": "invalid_media_path", "error": str(exc)}

    accounts = _select_accounts_for_auto_publish(session)
    if platforms is not None:
        accounts = [account for account in accounts if account.platform in platforms]
    if not accounts:
        return {"skipped": True, "reason": "no_active_accounts"}

    from services.publishing.schedule import (
        existing_article_slot,
        load_spacing_config,
        next_auto_slot,
    )

    spacing = load_spacing_config(config)
    try:
        slot = existing_article_slot(session, article_id=article.id)
        if slot is None:
            slot = next_auto_slot(session, config=spacing)
    except Exception as exc:
        logger.error("auto_publish schedule failed article=%s: {}", article.id, exc)
        return {"skipped": True, "reason": "schedule_failed", "error": str(exc)}

    created: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    draft = draft_from_video_draft(_parse_video_draft(article))
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
            job = create_ingestion_publish_job(
                session,
                article=article,
                account=account,
                scheduled_at=slot,
                media_paths=(video_path, cover_path),
                draft=draft,
            )
        except PlatformNotFoundError as exc:
            skipped.append(
                {"account_id": account.id, "platform": account.platform, "reason": str(exc)}
            )
            continue
        except PublishPayloadError as exc:
            skipped.append(
                {
                    "account_id": account.id,
                    "platform": account.platform,
                    "reason": exc.reason,
                }
            )
            continue
        created.append(
            {
                "job_id": job.id,
                "account_id": account.id,
                "platform": account.platform,
            }
        )
        logger.info(
            "auto_publish enqueued job=%s article=%s platform=%s scheduled_at=%s",
            job.id,
            article.id,
            account.platform,
            slot.isoformat(),
        )

    if created:
        return {"enqueued": True, "jobs": created, "skipped": skipped}
    return {"skipped": True, "reason": "nothing_created", "details": skipped, "jobs": [], "enqueued": False}
