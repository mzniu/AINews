"""Tests for metrics summary aggregation."""
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.query import get_metrics_summary
from services.publishing.metrics.snapshot_store import upsert_metric_snapshot
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models import publishing_metrics  # noqa: F401


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_get_metrics_summary_aggregates_by_platform():
    session = _session()
    now = datetime.utcnow()
    session.add(
        PublisherAccount(
            id="acc1",
            platform="douyin",
            nickname="抖音号",
            platform_uid="dy1",
            session_path="data/publish/sessions/acc1.enc",
        )
    )
    session.add(
        PublisherAccount(
            id="acc2",
            platform="xiaohongshu",
            nickname="小红书号",
            platform_uid="xhs1",
            session_path="data/publish/sessions/acc2.enc",
        )
    )
    session.flush()
    session.add(
        PublishJob(
            id="job1",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="抖音作品",
            status="published",
            published_at=now - timedelta(days=2),
        )
    )
    session.add(
        PublishJob(
            id="job2",
            account_id="acc2",
            video_path="data/videos/b.mp4",
            title="小红书作品",
            status="published",
            published_at=now - timedelta(days=1),
        )
    )
    session.flush()
    snap_date = now.date()
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="douyin",
        snapshot_date=snap_date,
        metrics=PostMetricsItem(platform_post_id="v1", view_count=1000, like_count=50, comment_count=5),
    )
    upsert_metric_snapshot(
        session,
        job_id="job2",
        account_id="acc2",
        platform="xiaohongshu",
        snapshot_date=snap_date,
        metrics=PostMetricsItem(platform_post_id="n1", view_count=500, like_count=20, comment_count=2),
    )
    session.commit()

    summary = get_metrics_summary(session, days=30)
    assert summary["totals"]["posts_total"] == 2
    assert summary["totals"]["posts_with_metrics"] == 2
    assert summary["totals"]["view_count"] == 1500
    assert summary["totals"]["like_count"] == 70
    assert summary["totals"]["comment_count"] == 7

    by_platform = {row["platform"]: row for row in summary["by_platform"]}
    assert by_platform["douyin"]["view_count"] == 1000
    assert by_platform["xiaohongshu"]["view_count"] == 500


def test_get_metrics_summary_filters_platform():
    session = _session()
    now = datetime.utcnow()
    session.add(
        PublisherAccount(
            id="acc1",
            platform="douyin",
            nickname="抖音号",
            platform_uid="dy1",
            session_path="data/publish/sessions/acc1.enc",
        )
    )
    session.flush()
    session.add(
        PublishJob(
            id="job1",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="抖音作品",
            status="published",
            published_at=now,
        )
    )
    session.commit()
    summary = get_metrics_summary(session, platform="kuaishou", days=30)
    assert summary["totals"]["posts_total"] == 0
