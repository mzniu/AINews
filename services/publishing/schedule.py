"""Auto-publish spacing: per-article slots, quiet hours, reschedule."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.ingestion.article_scorer import load_scoring_config
from src.db.models.publishing import PublishJob

BJ = ZoneInfo("Asia/Shanghai")
INGESTION_SOURCE = "ingestion"
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class PublishSpacingConfig:
    interval_minutes: int = 60
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "07:00"


def load_spacing_config(cfg: dict[str, Any] | None = None) -> PublishSpacingConfig:
    active = cfg or load_scoring_config()
    auto = (active.get("post_score_automation") or {}).get("auto_publish") or {}
    qh = auto.get("quiet_hours") or {}
    try:
        interval = int(auto.get("interval_minutes", 60))
    except (TypeError, ValueError):
        interval = 60
    interval = min(240, max(15, interval))
    return PublishSpacingConfig(
        interval_minutes=interval,
        quiet_hours_enabled=bool(qh.get("enabled", False)),
        quiet_hours_start=str(qh.get("start") or "23:00"),
        quiet_hours_end=str(qh.get("end") or "07:00"),
    )


def parse_schedule_datetime(value: datetime) -> datetime:
    """Normalize API datetime to UTC naive (same as POST /jobs)."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_hhmm(value: str) -> time:
    match = _HHMM_RE.match(str(value or "").strip())
    if not match:
        raise ValueError(f"invalid time: {value}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"invalid time: {value}")
    return time(hour, minute)


def _utc_naive_to_bj(dt: datetime) -> datetime:
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return aware.astimezone(BJ)


def _bj_to_utc_naive(bj: datetime) -> datetime:
    if bj.tzinfo is None:
        bj = bj.replace(tzinfo=BJ)
    return bj.astimezone(timezone.utc).replace(tzinfo=None)


def _wall_time_in_quiet(t: time, start: time, end: time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def in_quiet_hours(now_utc_naive: datetime, config: PublishSpacingConfig) -> bool:
    if not config.quiet_hours_enabled:
        return False
    start = _parse_hhmm(config.quiet_hours_start)
    end = _parse_hhmm(config.quiet_hours_end)
    bj = _utc_naive_to_bj(now_utc_naive)
    return _wall_time_in_quiet(bj.timetz().replace(tzinfo=None), start, end)


def clamp_quiet_hours(slot_utc_naive: datetime, config: PublishSpacingConfig) -> datetime:
    if not config.quiet_hours_enabled:
        return slot_utc_naive
    start = _parse_hhmm(config.quiet_hours_start)
    end = _parse_hhmm(config.quiet_hours_end)
    if start == end:
        return slot_utc_naive
    bj = _utc_naive_to_bj(slot_utc_naive)
    wall = bj.timetz().replace(tzinfo=None)
    if not _wall_time_in_quiet(wall, start, end):
        return slot_utc_naive
    end_date: date = bj.date()
    if start > end and wall >= start:
        end_date = bj.date() + timedelta(days=1)
    end_dt = datetime.combine(end_date, end, tzinfo=BJ)
    return _bj_to_utc_naive(end_dt)


def _occupied_slots(session: Session, *, exclude_source_id: str | None = None) -> list[datetime]:
    now = datetime.utcnow()
    query = session.query(PublishJob.scheduled_at).filter(
        PublishJob.status.in_(("pending", "uploading"))
    )
    if exclude_source_id:
        query = query.filter(
            (PublishJob.source_id.is_(None)) | (PublishJob.source_id != exclude_source_id)
        )
    rows = query.all()
    return [row[0] if row[0] is not None else now for row in rows]


def _last_success_at(session: Session) -> datetime | None:
    row = (
        session.query(func.coalesce(PublishJob.published_at, PublishJob.finished_at))
        .filter(PublishJob.status == "published")
        .order_by(func.coalesce(PublishJob.published_at, PublishJob.finished_at).desc())
        .first()
    )
    if not row or row[0] is None:
        return None
    return row[0]


def next_auto_slot(
    session: Session,
    *,
    config: PublishSpacingConfig,
    now: datetime | None = None,
    exclude_source_id: str | None = None,
) -> datetime:
    now = now or datetime.utcnow()
    interval = timedelta(minutes=config.interval_minutes)
    occupied = _occupied_slots(session, exclude_source_id=exclude_source_id)
    last_success = _last_success_at(session)

    if not occupied and not last_success:
        base = now
    else:
        anchor_candidates = list(occupied)
        if last_success is not None:
            anchor_candidates.append(last_success)
        base = max(now, max(anchor_candidates) + interval)

    slot = base
    for _ in range(64):
        slot = clamp_quiet_hours(slot, config)
        if occupied:
            need = max(now, max(occupied) + interval)
        else:
            need = now
        if slot < need:
            slot = need
            continue
        return slot
    return slot


def existing_article_slot(session: Session, *, article_id: str) -> datetime | None:
    row = (
        session.query(PublishJob.scheduled_at)
        .filter(
            PublishJob.source_type == INGESTION_SOURCE,
            PublishJob.source_id == article_id,
            PublishJob.status.in_(("pending", "uploading")),
        )
        .order_by(PublishJob.scheduled_at.asc())
        .first()
    )
    if row and row[0] is not None:
        return row[0]
    return None


def _article_group_slot(session: Session, source_id: str) -> datetime | None:
    row = (
        session.query(PublishJob.scheduled_at)
        .filter(
            PublishJob.source_type == INGESTION_SOURCE,
            PublishJob.source_id == source_id,
            PublishJob.status == "pending",
        )
        .order_by(PublishJob.scheduled_at.asc())
        .first()
    )
    return row[0] if row and row[0] is not None else None


def _pending_ingestion_groups(session: Session) -> list[tuple[str, datetime]]:
    rows = (
        session.query(PublishJob.source_id, func.min(PublishJob.scheduled_at))
        .filter(
            PublishJob.status == "pending",
            PublishJob.source_type == INGESTION_SOURCE,
            PublishJob.source_id.isnot(None),
        )
        .group_by(PublishJob.source_id)
        .all()
    )
    now = datetime.utcnow()
    groups: list[tuple[str, datetime]] = []
    for source_id, slot in rows:
        if not source_id:
            continue
        groups.append((str(source_id), slot if slot is not None else now))
    groups.sort(key=lambda item: item[1])
    return groups


def _set_group_slot(session: Session, source_id: str, slot: datetime) -> list[str]:
    jobs = (
        session.query(PublishJob)
        .filter(
            PublishJob.source_type == INGESTION_SOURCE,
            PublishJob.source_id == source_id,
            PublishJob.status == "pending",
        )
        .all()
    )
    updated: list[str] = []
    for job in jobs:
        job.scheduled_at = slot
        updated.append(job.id)
    return updated


def cascade_auto_jobs_after(
    session: Session,
    *,
    config: PublishSpacingConfig,
    anchor_source_id: str,
    old_slot: datetime,
    anchor_new_slot: datetime,
) -> list[str]:
    cascaded: list[str] = []
    later = [
        (source_id, slot)
        for source_id, slot in _pending_ingestion_groups(session)
        if source_id != anchor_source_id and slot >= old_slot
    ]
    interval = timedelta(minutes=config.interval_minutes)
    chain_anchor = anchor_new_slot
    for source_id, _ in later:
        candidate = max(datetime.utcnow(), chain_anchor + interval)
        candidate = clamp_quiet_hours(candidate, config)
        slot = next_auto_slot(
            session,
            config=config,
            now=candidate,
            exclude_source_id=source_id,
        )
        session.flush()
        chain_anchor = slot
        cascaded.extend(_set_group_slot(session, source_id, slot))
    return cascaded


def reschedule_publish_job(
    session: Session,
    job: PublishJob,
    scheduled_at: datetime,
    *,
    config: PublishSpacingConfig,
    cascade: bool = True,
) -> dict[str, Any]:
    if job.status != "pending":
        raise ValueError("仅待发布任务可改期")
    slot = parse_schedule_datetime(scheduled_at)
    now = datetime.utcnow()
    if slot <= now:
        raise ValueError("定时发布时间必须晚于当前时间")

    old_slot = _article_group_slot(session, job.source_id) if job.source_id else job.scheduled_at
    if old_slot is None:
        old_slot = job.scheduled_at or now

    updated_ids: list[str] = []
    if job.source_type == INGESTION_SOURCE and job.source_id:
        updated_ids = _set_group_slot(session, job.source_id, slot)
    else:
        job.scheduled_at = slot
        updated_ids = [job.id]

    cascaded_ids: list[str] = []
    if cascade and job.source_type == INGESTION_SOURCE and job.source_id:
        cascaded_ids = cascade_auto_jobs_after(
            session,
            config=config,
            anchor_source_id=job.source_id,
            old_slot=old_slot,
            anchor_new_slot=slot,
        )

    return {
        "job_id": job.id,
        "scheduled_at": slot,
        "updated_job_ids": updated_ids,
        "cascaded_job_ids": cascaded_ids,
    }


def reshuffle_jobs_in_quiet_window(session: Session, *, config: PublishSpacingConfig) -> list[str]:
    """Re-slot pending ingestion groups whose slot falls inside the quiet window."""
    if not config.quiet_hours_enabled:
        return []
    reshuffled: list[str] = []
    for source_id, group_slot in list(_pending_ingestion_groups(session)):
        if not in_quiet_hours(group_slot, config):
            continue
        start = clamp_quiet_hours(max(datetime.utcnow(), group_slot), config)
        slot = next_auto_slot(
            session,
            config=config,
            now=start,
            exclude_source_id=source_id,
        )
        while in_quiet_hours(slot, config):
            slot = clamp_quiet_hours(slot + timedelta(minutes=1), config)
        reshuffled.extend(_set_group_slot(session, source_id, slot))
    session.flush()
    return reshuffled
