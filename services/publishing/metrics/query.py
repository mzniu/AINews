"""Query helpers for published post metrics."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from services.publishing.metrics.snapshot_store import get_latest_metrics_by_job_ids
from services.publishing.registry import get_platform_config, PlatformNotFoundError
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models.publishing_metrics import PublishMetricsSyncRun, PublishPostMetricSnapshot


def list_published_posts(
    session: Session,
    *,
    platform: str | None = None,
    account_id: str | None = None,
    days: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = (
        session.query(PublishJob, PublisherAccount)
        .join(PublisherAccount, PublishJob.account_id == PublisherAccount.id)
        .filter(PublishJob.status == "published")
        .order_by(PublishJob.published_at.desc())
    )
    if platform:
        query = query.filter(PublisherAccount.platform == platform)
    if account_id:
        query = query.filter(PublishJob.account_id == account_id)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(PublishJob.published_at >= cutoff)

    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    job_ids = [job.id for job, _ in rows]
    latest = get_latest_metrics_by_job_ids(session, job_ids)

    items: list[dict] = []
    for job, account in rows:
        snap = latest.get(job.id)
        try:
            platform_display_name = get_platform_config(account.platform).get(
                "display_name", account.platform
            )
        except PlatformNotFoundError:
            platform_display_name = account.platform
        items.append(_serialize_published_post(job, account, platform_display_name, snap))
    return items, total


def _serialize_published_post(job, account, platform_display_name, snap) -> dict:
    metrics = None
    if snap is not None:
        metrics = {
            "view_count": snap.view_count,
            "like_count": snap.like_count,
            "comment_count": snap.comment_count,
            "share_count": snap.share_count,
            "favorite_count": snap.favorite_count,
            "follow_count": snap.follow_count,
            "play_3s_rate": snap.play_3s_rate,
            "completion_rate": snap.completion_rate,
            "avg_watch_sec": snap.avg_watch_sec,
            "profile_click_count": snap.profile_click_count,
            "snapshot_date": snap.snapshot_date.isoformat() if snap.snapshot_date else None,
            "fetched_at": snap.fetched_at.isoformat() if snap.fetched_at else None,
        }
    return {
        "job_id": job.id,
        "title": job.title,
        "platform": account.platform,
        "platform_display_name": platform_display_name,
        "account_id": account.id,
        "account_nickname": account.nickname,
        "published_at": job.published_at.isoformat() if job.published_at else None,
        "platform_post_id": job.platform_post_id,
        "platform_post_url": job.platform_post_url,
        "metrics_match_status": job.metrics_match_status or "pending",
        "metrics_last_synced_at": job.metrics_last_synced_at.isoformat()
        if job.metrics_last_synced_at
        else None,
        "metrics": metrics,
    }


def get_post_metrics_history(
    session: Session,
    job_id: str,
    *,
    days: int = 30,
) -> list[dict]:
    cutoff = date.today() - timedelta(days=days)
    rows = (
        session.query(PublishPostMetricSnapshot)
        .filter(
            PublishPostMetricSnapshot.job_id == job_id,
            PublishPostMetricSnapshot.snapshot_date >= cutoff,
        )
        .order_by(PublishPostMetricSnapshot.snapshot_date.asc())
        .all()
    )
    return [
        {
            "snapshot_date": row.snapshot_date.isoformat(),
            "view_count": row.view_count,
            "like_count": row.like_count,
            "comment_count": row.comment_count,
            "share_count": row.share_count,
            "favorite_count": row.favorite_count,
            "follow_count": row.follow_count,
            "play_3s_rate": row.play_3s_rate,
            "completion_rate": row.completion_rate,
            "avg_watch_sec": row.avg_watch_sec,
            "profile_click_count": row.profile_click_count,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }
        for row in rows
    ]


def get_latest_sync_run(session: Session) -> PublishMetricsSyncRun | None:
    return (
        session.query(PublishMetricsSyncRun)
        .order_by(PublishMetricsSyncRun.started_at.desc())
        .first()
    )


def _empty_totals() -> dict:
    return {
        "posts_total": 0,
        "posts_with_metrics": 0,
        "view_count": 0,
        "like_count": 0,
        "comment_count": 0,
        "share_count": 0,
        "favorite_count": 0,
    }


def _add_metric_fields(target: dict, snap: PublishPostMetricSnapshot) -> None:
    if snap.view_count:
        target["view_count"] += snap.view_count
    if snap.like_count:
        target["like_count"] += snap.like_count
    if snap.comment_count:
        target["comment_count"] += snap.comment_count
    if snap.share_count:
        target["share_count"] += snap.share_count
    if snap.favorite_count:
        target["favorite_count"] += snap.favorite_count


def get_metrics_summary(
    session: Session,
    *,
    platform: str | None = None,
    account_id: str | None = None,
    days: int = 30,
) -> dict:
    query = (
        session.query(PublishJob, PublisherAccount)
        .join(PublisherAccount, PublishJob.account_id == PublisherAccount.id)
        .filter(PublishJob.status == "published")
    )
    if platform:
        query = query.filter(PublisherAccount.platform == platform)
    if account_id:
        query = query.filter(PublishJob.account_id == account_id)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(PublishJob.published_at >= cutoff)

    rows = query.all()
    job_ids = [job.id for job, _ in rows]
    latest = get_latest_metrics_by_job_ids(session, job_ids)

    totals = _empty_totals()
    totals["posts_total"] = len(rows)
    platform_buckets: dict[str, dict] = {}

    for job, account in rows:
        snap = latest.get(job.id)
        plat = account.platform
        if plat not in platform_buckets:
            try:
                display_name = get_platform_config(plat).get("display_name", plat)
            except PlatformNotFoundError:
                display_name = plat
            platform_buckets[plat] = {
                "platform": plat,
                "platform_display_name": display_name,
                **_empty_totals(),
            }
        bucket = platform_buckets[plat]
        bucket["posts_total"] += 1
        if snap is None:
            continue
        totals["posts_with_metrics"] += 1
        bucket["posts_with_metrics"] += 1
        _add_metric_fields(totals, snap)
        _add_metric_fields(bucket, snap)

    by_platform = sorted(
        platform_buckets.values(),
        key=lambda row: row.get("view_count", 0),
        reverse=True,
    )
    return {"totals": totals, "by_platform": by_platform}


def bind_published_post(
    session: Session,
    *,
    job_id: str,
    platform_post_id: str,
    platform_post_url: str | None = None,
) -> dict:
    job = session.get(PublishJob, job_id)
    if job is None or job.status != "published":
        raise ValueError("已发布作品不存在")
    post_id = (platform_post_id or "").strip()
    if not post_id:
        raise ValueError("platform_post_id 不能为空")

    account = session.get(PublisherAccount, job.account_id)
    if account is None:
        raise ValueError("账号不存在")

    job.platform_post_id = post_id
    if platform_post_url:
        job.platform_post_url = platform_post_url.strip() or None
    elif account.platform == "xiaohongshu":
        from services.publishing.metrics.post_id import build_xiaohongshu_post_url

        job.platform_post_url = build_xiaohongshu_post_url(post_id)
    elif account.platform == "douyin":
        from services.publishing.metrics.post_id import build_douyin_post_url

        job.platform_post_url = build_douyin_post_url(post_id)
    elif account.platform == "kuaishou":
        from services.publishing.metrics.post_id import build_kuaishou_post_url

        job.platform_post_url = build_kuaishou_post_url(post_id)

    job.metrics_match_status = "manual_matched"
    job.metrics_last_synced_at = datetime.utcnow()
    session.flush()
    return {
        "job_id": job.id,
        "platform_post_id": job.platform_post_id,
        "platform_post_url": job.platform_post_url,
        "metrics_match_status": job.metrics_match_status,
    }
