"""Policy candidate evaluation and budgeted publish dispatch."""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from services.ingestion.article_scorer import load_scoring_config
from services.publishing.auto_publish import (
    SOURCE_TYPE,
    create_ingestion_publish_job,
)
from services.publishing.platform_jobs import (
    eligible_video_platform_ids,
    pick_account_for_platform,
)
from services.publishing.publish_policy import decide_platform_publish
from services.publishing.schedule import BJ, next_platform_slot, parse_schedule_datetime
from src.db.models.ingestion import IngestedArticle
from src.db.models.publishing import (
    AutoPublishCandidate,
    AutoPublishDispatchLease,
    PublishJob,
    PublisherAccount,
)

_ACTIVE_JOB_STATUSES = ("pending", "uploading", "published")
_DEFER_REEVALUATION = timedelta(hours=48)


def _load_breakdown(article: IngestedArticle) -> dict[str, Any]:
    try:
        value = json.loads(article.score_breakdown_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _score_inputs(article: IngestedArticle) -> dict[str, Any]:
    breakdown = _load_breakdown(article)
    industry = breakdown.get("industry") or {}
    viral = breakdown.get("viral") or {}
    final = breakdown.get("final") or {}
    return {
        "industry_grade": industry.get("grade")
        or final.get("industry_grade")
        or article.score_grade
        or "",
        "industry_total": industry.get("total")
        if industry.get("total") is not None
        else article.score_total or 0,
        "viral_grade": viral.get("grade") or final.get("viral_grade") or "",
        "viral_total": viral.get("total")
        if viral.get("total") is not None
        else final.get("viral_total") or 0,
        "motives": viral.get("motives") or [],
        "platform_fit": viral.get("platform_fit") or [],
    }


def _recent_story_count(
    session: Session,
    article: IngestedArticle,
    *,
    now: datetime,
) -> int:
    if not article.story_id:
        return 0
    return int(
        session.query(func.count(IngestedArticle.id))
        .filter(
            IngestedArticle.story_id == article.story_id,
            IngestedArticle.id != article.id,
            IngestedArticle.created_at >= now - timedelta(hours=24),
            IngestedArticle.created_at <= now,
        )
        .scalar()
        or 0
    )


def _candidate_payload(row: AutoPublishCandidate) -> dict[str, Any]:
    return {
        "candidate_id": row.id,
        "article_id": row.article_id,
        "platform": row.platform,
        "action": row.action,
        "recommended_action": row.recommended_action,
        "priority": row.priority,
        "status": row.status,
        "policy_version": row.policy_version,
    }


def evaluate_article_candidates(
    session: Session,
    article: IngestedArticle,
    config: dict[str, Any],
    *,
    now: datetime | None = None,
    platforms: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Evaluate and idempotently persist one candidate per eligible platform."""
    policy = config.get("publish_policy") or {}
    if not policy.get("enabled", False):
        return {
            "candidate_evaluation": False,
            "skipped": True,
            "reason": "publish_policy_disabled",
            "candidates": [],
        }

    evaluated_at = parse_schedule_datetime(now or datetime.utcnow())
    recent_count = _recent_story_count(session, article, now=evaluated_at)
    inputs = _score_inputs(article)
    configured = policy.get("platforms") or {}
    requested = set(platforms) if platforms is not None else None
    selected_platforms = [
        platform
        for platform in eligible_video_platform_ids()
        if platform in configured and (requested is None or platform in requested)
    ]
    rows: list[AutoPublishCandidate] = []
    for platform in selected_platforms:
        version = str(policy.get("policy_version", 1))
        row = (
            session.query(AutoPublishCandidate)
            .filter_by(
                article_id=article.id,
                platform=platform,
                policy_version=version,
            )
            .one_or_none()
        )
        if row is not None:
            if row.status in {"skipped", "dispatched"}:
                rows.append(row)
                continue
            if (
                row.status == "deferred"
                and row.evaluated_at is not None
                and evaluated_at - row.evaluated_at < _DEFER_REEVALUATION
            ):
                rows.append(row)
                continue

        decision = decide_platform_publish(
            platform,
            **inputs,
            story_recent_count=recent_count,
            config=config,
        )
        version = str(decision.policy_version)
        status = {
            "publish": "pending",
            "defer": "deferred",
            "skip": "skipped",
        }[decision.action]
        if row is None:
            row = AutoPublishCandidate(
                article_id=article.id,
                platform=platform,
                policy_version=version,
                action=decision.action,
                recommended_action=decision.recommended_action,
                priority=decision.priority,
                reasons_json=json.dumps(decision.reasons, ensure_ascii=False),
                status=status,
                evaluated_at=evaluated_at,
                industry_id=article.industry_id,
            )
            session.add(row)
        else:
            row.industry_id = article.industry_id
            row.action = decision.action
            row.recommended_action = decision.recommended_action
            row.priority = decision.priority
            row.reasons_json = json.dumps(decision.reasons, ensure_ascii=False)
            row.status = status
            row.evaluated_at = evaluated_at
            row.scheduled_date = None
            row.publish_job_id = None
        session.flush()
        rows.append(row)

    return {
        "candidate_evaluation": True,
        "article_id": article.id,
        "policy_version": str(policy.get("policy_version", 1)),
        "candidates": [_candidate_payload(row) for row in rows],
    }


def _append_reason(candidate: AutoPublishCandidate, reason: str) -> None:
    try:
        reasons = json.loads(candidate.reasons_json or "[]")
    except (TypeError, json.JSONDecodeError):
        reasons = []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    reasons.append(reason)
    candidate.reasons_json = json.dumps(reasons, ensure_ascii=False)


def _existing_platform_job(
    session: Session,
    *,
    article_id: str,
    platform: str,
) -> PublishJob | None:
    return (
        session.query(PublishJob)
        .join(PublisherAccount, PublishJob.account_id == PublisherAccount.id)
        .filter(
            PublishJob.source_type == SOURCE_TYPE,
            PublishJob.source_id == article_id,
            PublisherAccount.platform == platform,
            PublishJob.status.in_(_ACTIVE_JOB_STATUSES),
        )
        .order_by(PublishJob.created_at.asc())
        .first()
    )


def _beijing_date(value: datetime) -> date:
    aware = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return aware.astimezone(BJ).date()


def _claim_candidate(
    session: Session,
    candidate_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Atomically transition one pending candidate to dispatching."""
    changed = (
        session.query(AutoPublishCandidate)
        .filter(
            AutoPublishCandidate.id == candidate_id,
            AutoPublishCandidate.status == "pending",
        )
        .update(
            {
                AutoPublishCandidate.status: "dispatching",
                AutoPublishCandidate.updated_at: now or datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    session.flush()
    return changed == 1


def _reconcile_dispatched_candidates(
    session: Session,
    *,
    policy_version: str,
    now: datetime,
) -> None:
    rows = (
        session.query(AutoPublishCandidate)
        .filter_by(status="dispatched")
        .all()
    )
    for candidate in rows:
        job = (
            session.get(PublishJob, candidate.publish_job_id)
            if candidate.publish_job_id
            else None
        )
        if job is not None and job.status in _ACTIVE_JOB_STATUSES:
            continue
        state = job.status if job is not None else "missing"
        if state not in {"failed", "cancelled", "missing"}:
            continue
        if candidate.policy_version == policy_version:
            candidate.status = "pending"
        else:
            candidate.status = "deferred"
            candidate.evaluated_at = now - _DEFER_REEVALUATION
        candidate.publish_job_id = None
        candidate.scheduled_date = None
        _append_reason(candidate, f"reconcile.{state}")
    session.flush()


def _reevaluate_due_deferred(
    session: Session,
    *,
    now: datetime,
    config: dict[str, Any],
) -> None:
    due = (
        session.query(AutoPublishCandidate)
        .filter(
            AutoPublishCandidate.status == "deferred",
            AutoPublishCandidate.evaluated_at <= now - _DEFER_REEVALUATION,
        )
        .order_by(AutoPublishCandidate.evaluated_at.asc())
        .all()
    )
    for candidate in due:
        article = session.get(IngestedArticle, candidate.article_id)
        if article is None:
            _append_reason(candidate, "reevaluate.failed:article_missing")
            candidate.evaluated_at = now
            continue
        evaluate_article_candidates(
            session,
            article,
            config,
            now=now,
            platforms=(candidate.platform,),
        )
    session.flush()


def _acquire_dispatch_lease(
    session: Session,
    *,
    platform: str,
    dispatch_date: date,
    now: datetime,
    lease_seconds: int,
) -> str | None:
    """Atomically acquire or take over an expired platform/day lease."""
    owner_id = uuid.uuid4().hex
    expires_at = now + timedelta(seconds=max(30, lease_seconds))
    values = {
        "id": uuid.uuid4().hex,
        "platform": platform,
        "dispatch_date": dispatch_date,
        "owner_id": owner_id,
        "acquired_at": now,
        "expires_at": expires_at,
        "created_at": now,
        "updated_at": now,
    }
    if session.get_bind().dialect.name == "sqlite":
        statement = sqlite_insert(AutoPublishDispatchLease).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=["platform", "dispatch_date"],
            set_={
                "owner_id": owner_id,
                "acquired_at": now,
                "expires_at": expires_at,
                "updated_at": now,
            },
            where=AutoPublishDispatchLease.expires_at <= now,
        )
        changed = session.execute(statement).rowcount
    else:
        existing = (
            session.query(AutoPublishDispatchLease)
            .filter_by(platform=platform, dispatch_date=dispatch_date)
            .with_for_update()
            .one_or_none()
        )
        if existing is not None and existing.expires_at > now:
            return None
        if existing is None:
            session.add(AutoPublishDispatchLease(**values))
        else:
            existing.owner_id = owner_id
            existing.acquired_at = now
            existing.expires_at = expires_at
        changed = 1
    session.flush()
    return owner_id if changed == 1 else None


def _release_dispatch_lease(
    session: Session,
    *,
    platform: str,
    dispatch_date: date,
    owner_id: str,
) -> None:
    session.query(AutoPublishDispatchLease).filter_by(
        platform=platform,
        dispatch_date=dispatch_date,
        owner_id=owner_id,
    ).delete(synchronize_session=False)
    session.flush()


def _dispatch_platform_candidates(
    session: Session,
    *,
    platform: str,
    platform_config: dict[str, Any],
    policy_version: str,
    target_date: date,
    now: datetime,
    config: dict[str, Any],
    dispatched: list[dict[str, Any]],
    deferred: list[dict[str, Any]],
) -> None:
    candidates = (
        session.query(AutoPublishCandidate)
        .filter_by(
            platform=platform,
            status="pending",
            policy_version=policy_version,
        )
        .order_by(
            AutoPublishCandidate.priority.desc(),
            AutoPublishCandidate.evaluated_at.asc(),
            AutoPublishCandidate.created_at.asc(),
        )
        .all()
    )
    for candidate in candidates:
        if not _claim_candidate(session, candidate.id, now=now):
            continue
        session.expire(candidate)
        existing = _existing_platform_job(
            session,
            article_id=candidate.article_id,
            platform=platform,
        )
        if existing is not None:
            candidate.status = "dispatched"
            candidate.publish_job_id = existing.id
            candidate.scheduled_date = _beijing_date(
                existing.scheduled_at or now
            )
            dispatched.append(
                {
                    "candidate_id": candidate.id,
                    "article_id": candidate.article_id,
                    "platform": platform,
                    "job_id": existing.id,
                    "existing": True,
                }
            )
            continue

        slot = next_platform_slot(
            session,
            platform,
            target_date,
            platform_config,
            now=now,
            config=config,
        )
        if slot is None:
            candidate.status = "pending"
            session.flush()
            break
        article = session.get(IngestedArticle, candidate.article_id)
        account = pick_account_for_platform(session, platform)
        if article is None or account is None or account.status != "active":
            candidate.status = "deferred"
            candidate.evaluated_at = now
            reason = (
                "dispatch.failed:article_missing"
                if article is None
                else "dispatch.failed:account_unavailable"
            )
            _append_reason(candidate, reason)
            deferred.append(
                {
                    "candidate_id": candidate.id,
                    "article_id": candidate.article_id,
                    "platform": platform,
                    "reason": reason,
                }
            )
            continue

        try:
            with session.begin_nested():
                job = create_ingestion_publish_job(
                    session,
                    article=article,
                    account=account,
                    scheduled_at=slot,
                )
        except Exception as exc:
            candidate.status = "deferred"
            candidate.evaluated_at = now
            reason = f"dispatch.failed:{type(exc).__name__}:{exc}"
            _append_reason(candidate, reason)
            deferred.append(
                {
                    "candidate_id": candidate.id,
                    "article_id": candidate.article_id,
                    "platform": platform,
                    "reason": reason,
                }
            )
            logger.warning(
                "Candidate dispatch deferred candidate={} platform={}: {}",
                candidate.id,
                platform,
                exc,
            )
            continue

        candidate.status = "dispatched"
        candidate.publish_job_id = job.id
        candidate.scheduled_date = target_date
        dispatched.append(
            {
                "candidate_id": candidate.id,
                "article_id": candidate.article_id,
                "platform": platform,
                "job_id": job.id,
                "scheduled_at": slot.isoformat(),
            }
        )


def dispatch_daily_candidates(
    session: Session,
    now: datetime | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch highest-priority candidates without exceeding today's budgets."""
    from services.publishing.metrics.mature_metrics import get_pending_queue_stats
    from services.publishing.rollout_guard import (
        evaluate_queue_backpressure,
        should_dispatch_platform,
    )

    active = config or load_scoring_config()
    policy = active.get("publish_policy") or {}
    if not policy.get("enabled", False):
        return {"dispatched": [], "deferred": [], "reason": "publish_policy_disabled"}

    now_utc = parse_schedule_datetime(now or datetime.utcnow())
    target_date = _beijing_date(now_utc)
    policy_version = str(policy.get("policy_version", 1))
    dispatched: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    eligible = set(eligible_video_platform_ids())

    rollout = policy.get("rollout") or {}
    max_queue_days = float(rollout.get("max_queue_days", 2))
    queue_stats = get_pending_queue_stats(session, now=now_utc)
    oldest_at = None
    if queue_stats.get("oldest_at"):
        oldest_at = datetime.fromisoformat(str(queue_stats["oldest_at"]))
    backpressure = evaluate_queue_backpressure(
        oldest_pending_at=oldest_at,
        now=now_utc,
        max_queue_days=max_queue_days,
    )
    if backpressure.stop_new_dispatch:
        return {
            "dispatch_date": target_date.isoformat(),
            "dispatched": [],
            "deferred": [],
            "reason": "queue_backpressure",
            "queue": queue_stats,
        }

    _reconcile_dispatched_candidates(
        session,
        policy_version=policy_version,
        now=now_utc,
    )
    _reevaluate_due_deferred(
        session,
        now=now_utc,
        config=active,
    )

    skipped_platforms: list[str] = []
    for platform, platform_config in (policy.get("platforms") or {}).items():
        if (
            platform not in eligible
            or not isinstance(platform_config, dict)
        ):
            continue
        if not should_dispatch_platform(platform, policy):
            skipped_platforms.append(platform)
            continue
        owner_id = _acquire_dispatch_lease(
            session,
            platform=platform,
            dispatch_date=target_date,
            now=now_utc,
            lease_seconds=int(policy.get("dispatch_lease_seconds", 120)),
        )
        if owner_id is None:
            continue
        try:
            _dispatch_platform_candidates(
                session,
                platform=platform,
                platform_config=platform_config,
                policy_version=policy_version,
                target_date=target_date,
                now=now_utc,
                config=active,
                dispatched=dispatched,
                deferred=deferred,
            )
        finally:
            _release_dispatch_lease(
                session,
                platform=platform,
                dispatch_date=target_date,
                owner_id=owner_id,
            )

    session.flush()
    return {
        "dispatch_date": target_date.isoformat(),
        "dispatched": dispatched,
        "deferred": deferred,
        "skipped_platforms": skipped_platforms,
        "queue": queue_stats,
    }


def skip_candidate(session: Session, candidate_id: str) -> AutoPublishCandidate:
    """Mark one candidate as skipped by ID."""
    candidate = session.get(AutoPublishCandidate, candidate_id)
    if candidate is None:
        raise ValueError("candidate not found")
    candidate.status = "skipped"
    candidate.updated_at = datetime.utcnow()
    session.flush()
    return candidate


def enqueue_candidate(session: Session, candidate_id: str, *, config: dict[str, Any] | None = None) -> AutoPublishCandidate:
    """Dispatch a single candidate to a PublishJob, bypassing daily budgets."""
    candidate = session.get(AutoPublishCandidate, candidate_id)
    if candidate is None:
        raise ValueError("candidate not found")
    if candidate.status not in {"pending", "deferred"}:
        raise ValueError(f"candidate status is {candidate.status}, cannot enqueue")

    from services.publishing.platform_jobs import pick_account_for_platform
    from services.publishing.schedule import next_platform_slot, parse_schedule_datetime

    active = config or load_scoring_config()
    policy = active.get("publish_policy") or {}
    platform_config = (policy.get("platforms") or {}).get(candidate.platform) or {}

    now_utc = parse_schedule_datetime(datetime.utcnow())
    target_date = _beijing_date(now_utc)
    policy_version = str(policy.get("policy_version", 1))

    article = session.get(IngestedArticle, candidate.article_id)
    if article is None:
        candidate.status = "deferred"
        candidate.evaluated_at = now_utc
        _append_reason(candidate, "dispatch.failed:article_missing")
        session.flush()
        raise ValueError("article not found")

    account = pick_account_for_platform(session, candidate.platform)
    if account is None or account.status != "active":
        candidate.status = "deferred"
        candidate.evaluated_at = now_utc
        _append_reason(candidate, "dispatch.failed:account_unavailable")
        session.flush()
        raise ValueError("active account not found")

    slot = None
    for day_offset in range(14):
        probe_date = target_date + timedelta(days=day_offset)
        slot = next_platform_slot(
            session,
            candidate.platform,
            probe_date,
            platform_config,
            now=now_utc,
            config=active,
            ignore_daily_limit=True,
        )
        if slot is not None:
            break
    if slot is None:
        from services.publishing.schedule import load_spacing_config, next_auto_slot

        try:
            slot = next_auto_slot(
                session,
                config=load_spacing_config(active),
                now=now_utc,
                exclude_source_id=candidate.article_id,
            )
        except Exception:
            slot = None
    if slot is None:
        candidate.status = "deferred"
        candidate.evaluated_at = now_utc
        _append_reason(candidate, "dispatch.failed:no_slot")
        session.flush()
        raise ValueError("no available slot")

    job = create_ingestion_publish_job(
        session,
        article=article,
        account=account,
        scheduled_at=slot,
    )
    candidate.status = "dispatched"
    candidate.publish_job_id = job.id
    candidate.scheduled_date = target_date
    session.flush()
    return candidate
