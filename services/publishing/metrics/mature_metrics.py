"""Mature D1/D3 publish metrics and pending queue stats."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.db.models.publishing import PublishJob
from src.db.models.publishing_metrics import PublishPostMetricSnapshot

DEFAULT_HORIZONS = (24, 72)
COUNT_METRICS = ("like", "comment", "share", "favorite", "follow")


def _empty_summary() -> dict:
    return {
        "sample_size": 0,
        "median_views": None,
        "mean_views": None,
        "hit_rate_1k": None,
        "hit_rate_10k": None,
        "completion_rate": None,
        "average_watch_seconds": None,
        "engagement_rates": {metric: None for metric in (*COUNT_METRICS, "total")},
    }


def _mean_present(rows: Sequence[PublishPostMetricSnapshot], attr: str) -> float | None:
    values = [
        float(getattr(row, attr))
        for row in rows
        if getattr(row, attr, None) is not None
    ]
    return statistics.fmean(values) if values else None


def _metric_summary(rows: Sequence[PublishPostMetricSnapshot]) -> dict:
    if not rows:
        return _empty_summary()
    views = [int(row.view_count or 0) for row in rows]
    total_views = sum(views)
    count_totals = {
        "like": sum(int(row.like_count or 0) for row in rows),
        "comment": sum(int(row.comment_count or 0) for row in rows),
        "share": sum(int(row.share_count or 0) for row in rows),
        "favorite": sum(int(row.favorite_count or 0) for row in rows),
        "follow": sum(int(row.follow_count or 0) for row in rows),
    }
    engagement_rates = {
        metric: (count_totals[metric] / total_views if total_views else None)
        for metric in COUNT_METRICS
    }
    engagement_rates["total"] = (
        sum(count_totals.values()) / total_views if total_views else None
    )
    return {
        "sample_size": len(rows),
        "median_views": statistics.median(views),
        "mean_views": statistics.fmean(views),
        "hit_rate_1k": sum(view >= 1_000 for view in views) / len(views),
        "hit_rate_10k": sum(view >= 10_000 for view in views) / len(views),
        "completion_rate": _mean_present(rows, "completion_rate"),
        "average_watch_seconds": _mean_present(rows, "avg_watch_sec"),
        "engagement_rates": engagement_rates,
    }


def _first_mature_snapshots(
    session: Session,
    *,
    platform: str,
    horizon_hours: int,
    published_after: datetime | None,
    published_before: datetime | None,
) -> list[PublishPostMetricSnapshot]:
    jobs = (
        session.query(PublishJob)
        .filter(
            PublishJob.status == "published",
            PublishJob.published_at.isnot(None),
        )
        .join(
            PublishPostMetricSnapshot,
            PublishPostMetricSnapshot.job_id == PublishJob.id,
        )
        .filter(PublishPostMetricSnapshot.platform == platform)
    )
    if published_after is not None:
        jobs = jobs.filter(PublishJob.published_at >= published_after)
    if published_before is not None:
        jobs = jobs.filter(PublishJob.published_at < published_before)

    job_ids = [job.id for job in jobs.distinct().all()]
    if not job_ids:
        return []

    selected: list[PublishPostMetricSnapshot] = []
    for job_id in job_ids:
        job = session.get(PublishJob, job_id)
        if job is None or job.published_at is None:
            continue
        maturity_at = job.published_at + timedelta(hours=horizon_hours)
        row = (
            session.query(PublishPostMetricSnapshot)
            .filter(
                PublishPostMetricSnapshot.job_id == job_id,
                PublishPostMetricSnapshot.fetched_at >= maturity_at,
            )
            .order_by(
                PublishPostMetricSnapshot.fetched_at.asc(),
                PublishPostMetricSnapshot.id.asc(),
            )
            .first()
        )
        if row is not None:
            selected.append(row)
    return selected


def get_mature_platform_metrics(
    session: Session,
    *,
    platforms: Iterable[str] | None = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> dict[str, dict[str, dict]]:
    """Return first mature snapshot metrics per platform and horizon."""
    selected_platforms = list(platforms or [])
    if not selected_platforms:
        selected_platforms = [
            str(value)
            for (value,) in session.query(PublishPostMetricSnapshot.platform)
            .distinct()
            .order_by(PublishPostMetricSnapshot.platform.asc())
            .all()
            if value
        ]
    result: dict[str, dict[str, dict]] = {}
    for platform in selected_platforms:
        result[platform] = {}
        for horizon in horizons:
            rows = _first_mature_snapshots(
                session,
                platform=platform,
                horizon_hours=int(horizon),
                published_after=published_after,
                published_before=published_before,
            )
            result[platform][f"{int(horizon)}h"] = _metric_summary(rows)
    return result


def get_pending_queue_stats(
    session: Session,
    *,
    now: datetime | None = None,
) -> dict:
    """Summarize pending publish jobs and oldest queue age in days."""
    current = now or datetime.utcnow()
    job_count = (
        session.query(func.count(PublishJob.id))
        .filter(PublishJob.status == "pending")
        .scalar()
        or 0
    )
    unique_video_count = (
        session.query(func.count(func.distinct(PublishJob.video_path)))
        .filter(PublishJob.status == "pending")
        .scalar()
        or 0
    )
    oldest_expr = func.min(func.coalesce(PublishJob.scheduled_at, PublishJob.created_at))
    oldest_at = (
        session.query(oldest_expr)
        .filter(PublishJob.status == "pending")
        .scalar()
    )
    oldest_age_days = None
    if oldest_at is not None:
        oldest_age_days = max(0.0, (current - oldest_at).total_seconds() / 86_400)
    return {
        "job_count": int(job_count),
        "unique_video_count": int(unique_video_count),
        "oldest_at": oldest_at.isoformat() if oldest_at is not None else None,
        "oldest_age_days": oldest_age_days,
        "estimated_days": oldest_age_days,
    }
