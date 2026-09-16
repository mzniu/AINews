"""Metrics snapshot persistence."""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy.orm import Session

from services.publishing.metrics.adapters.base import PostMetricsItem
from src.db.models.publishing_metrics import PublishPostMetricSnapshot


def upsert_metric_snapshot(
    session: Session,
    *,
    job_id: str,
    account_id: str,
    platform: str,
    snapshot_date: date,
    metrics: PostMetricsItem,
) -> PublishPostMetricSnapshot:
    row = (
        session.query(PublishPostMetricSnapshot)
        .filter_by(job_id=job_id, snapshot_date=snapshot_date)
        .one_or_none()
    )
    if row is None:
        row = PublishPostMetricSnapshot(
            job_id=job_id,
            account_id=account_id,
            platform=platform,
            snapshot_date=snapshot_date,
        )
        session.add(row)

    row.view_count = metrics.view_count
    row.like_count = metrics.like_count
    row.comment_count = metrics.comment_count
    row.share_count = metrics.share_count
    row.favorite_count = metrics.favorite_count
    row.follow_count = metrics.follow_count
    row.play_3s_rate = metrics.play_3s_rate
    row.completion_rate = metrics.completion_rate
    row.avg_watch_sec = metrics.avg_watch_sec
    row.profile_click_count = metrics.profile_click_count
    row.raw_json = json.dumps(metrics.raw or {}, ensure_ascii=False)
    row.fetched_at = datetime.utcnow()
    session.flush()
    return row


def get_latest_metrics_by_job_ids(
    session: Session,
    job_ids: list[str],
) -> dict[str, PublishPostMetricSnapshot]:
    if not job_ids:
        return {}
    rows = (
        session.query(PublishPostMetricSnapshot)
        .filter(PublishPostMetricSnapshot.job_id.in_(job_ids))
        .order_by(
            PublishPostMetricSnapshot.job_id.asc(),
            PublishPostMetricSnapshot.snapshot_date.desc(),
            PublishPostMetricSnapshot.fetched_at.desc(),
        )
        .all()
    )
    latest: dict[str, PublishPostMetricSnapshot] = {}
    for row in rows:
        if row.job_id not in latest:
            latest[row.job_id] = row
    return latest
