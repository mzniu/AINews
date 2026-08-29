"""Tests for metrics view-drop alerts."""
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.alerts import detect_view_drop_alerts
from services.publishing.metrics.snapshot_store import upsert_metric_snapshot
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models import publishing_metrics  # noqa: F401


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_detect_view_drop_alerts_flags_large_drop():
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
            title="骤降测试",
            status="published",
            published_at=now - timedelta(days=3),
        )
    )
    session.flush()
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="douyin",
        snapshot_date=(now - timedelta(days=2)).date(),
        metrics=PostMetricsItem(platform_post_id="v1", view_count=1000),
    )
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="douyin",
        snapshot_date=(now - timedelta(days=1)).date(),
        metrics=PostMetricsItem(platform_post_id="v1", view_count=500),
    )
    session.commit()

    alerts = detect_view_drop_alerts(session, drop_pct=30, min_previous_views=100)
    assert len(alerts) == 1
    assert alerts[0]["job_id"] == "job1"
    assert alerts[0]["previous_view_count"] == 1000
    assert alerts[0]["current_view_count"] == 500
    assert alerts[0]["drop_pct"] == 50.0


def test_detect_view_drop_alerts_ignores_small_baseline():
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
            title="小基数",
            status="published",
            published_at=now,
        )
    )
    session.flush()
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="douyin",
        snapshot_date=(now - timedelta(days=2)).date(),
        metrics=PostMetricsItem(platform_post_id="v1", view_count=50),
    )
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="douyin",
        snapshot_date=(now - timedelta(days=1)).date(),
        metrics=PostMetricsItem(platform_post_id="v1", view_count=10),
    )
    session.commit()

    alerts = detect_view_drop_alerts(session, drop_pct=30, min_previous_views=100)
    assert alerts == []
