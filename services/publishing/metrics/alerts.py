"""Detect view-count drop alerts between latest snapshots."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from services.publishing.metrics.query import list_published_posts
from src.db.models.publishing_metrics import PublishPostMetricSnapshot


def detect_view_drop_alerts(
    session: Session,
    *,
    drop_pct: float = 30.0,
    min_previous_views: int = 100,
    days: int = 30,
    platform: str | None = None,
    account_id: str | None = None,
) -> list[dict]:
    posts, _ = list_published_posts(
        session,
        platform=platform,
        account_id=account_id,
        days=days,
        limit=500,
        offset=0,
    )
    if not posts:
        return []

    job_ids = [post["job_id"] for post in posts]
    cutoff = date.today() - timedelta(days=days)
    rows = (
        session.query(PublishPostMetricSnapshot)
        .filter(
            PublishPostMetricSnapshot.job_id.in_(job_ids),
            PublishPostMetricSnapshot.snapshot_date >= cutoff,
            PublishPostMetricSnapshot.view_count.isnot(None),
        )
        .order_by(
            PublishPostMetricSnapshot.job_id.asc(),
            PublishPostMetricSnapshot.snapshot_date.desc(),
            PublishPostMetricSnapshot.fetched_at.desc(),
        )
        .all()
    )

    snapshots_by_job: dict[str, list[PublishPostMetricSnapshot]] = {}
    for row in rows:
        snapshots_by_job.setdefault(row.job_id, []).append(row)

    post_map = {post["job_id"]: post for post in posts}
    alerts: list[dict] = []

    for job_id, snaps in snapshots_by_job.items():
        if len(snaps) < 2:
            continue
        current, previous = snaps[0], snaps[1]
        prev_views = previous.view_count or 0
        curr_views = current.view_count or 0
        if prev_views < min_previous_views or curr_views >= prev_views:
            continue
        drop = prev_views - curr_views
        pct = round(drop / prev_views * 100, 1)
        if pct < drop_pct:
            continue
        post = post_map.get(job_id, {})
        alerts.append(
            {
                "job_id": job_id,
                "title": post.get("title", ""),
                "platform": post.get("platform"),
                "platform_display_name": post.get("platform_display_name"),
                "account_nickname": post.get("account_nickname"),
                "previous_snapshot_date": previous.snapshot_date.isoformat(),
                "current_snapshot_date": current.snapshot_date.isoformat(),
                "previous_view_count": prev_views,
                "current_view_count": curr_views,
                "drop_count": drop,
                "drop_pct": pct,
            }
        )

    alerts.sort(key=lambda item: item["drop_pct"], reverse=True)
    return alerts
