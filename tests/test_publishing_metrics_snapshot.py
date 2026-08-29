"""Tests for metrics snapshot persistence."""
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.snapshot_store import (
    get_latest_metrics_by_job_ids,
    upsert_metric_snapshot,
)
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models import publishing_metrics  # noqa: F401
from src.db.models.publishing_metrics import PublishPostMetricSnapshot


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_published_job(session, job_id: str = "job1") -> None:
    session.add(
        PublisherAccount(
            id="acc1",
            platform="xiaohongshu",
            nickname="测试",
            platform_uid="uid1",
            session_path="data/publish/sessions/acc1.enc",
        )
    )
    session.add(
        PublishJob(
            id=job_id,
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="测试标题",
            status="published",
            published_at=datetime(2026, 8, 10, 12, 0, 0),
        )
    )
    session.commit()


def test_upsert_metric_snapshot_creates_and_updates():
    session = _session()
    _seed_published_job(session)
    metrics = PostMetricsItem(
        platform_post_id="note1",
        title="测试标题",
        view_count=100,
        like_count=5,
        comment_count=1,
    )
    row1 = upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="xiaohongshu",
        snapshot_date=date(2026, 8, 11),
        metrics=metrics,
    )
    session.commit()
    assert row1.view_count == 100

    metrics.view_count = 150
    row2 = upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="xiaohongshu",
        snapshot_date=date(2026, 8, 11),
        metrics=metrics,
    )
    session.commit()
    assert row2.id == row1.id
    assert row2.view_count == 150
    assert session.query(PublishPostMetricSnapshot).count() == 1


def test_upsert_metric_snapshot_persists_funnel_fields():
    session = _session()
    _seed_published_job(session)
    row = upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="douyin",
        snapshot_date=date(2026, 8, 11),
        metrics=PostMetricsItem(
            platform_post_id="v1",
            view_count=1000,
            follow_count=8,
            play_3s_rate=41.0,
            completion_rate=22.5,
            avg_watch_sec=9.5,
            profile_click_count=3,
        ),
    )
    session.commit()
    assert row.follow_count == 8
    assert row.play_3s_rate == 41.0
    assert row.completion_rate == 22.5
    assert row.avg_watch_sec == 9.5
    assert row.profile_click_count == 3


def test_get_latest_metrics_by_job_ids():
    session = _session()
    _seed_published_job(session)
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="xiaohongshu",
        snapshot_date=date(2026, 8, 10),
        metrics=PostMetricsItem(platform_post_id="n1", view_count=10),
    )
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="xiaohongshu",
        snapshot_date=date(2026, 8, 11),
        metrics=PostMetricsItem(platform_post_id="n1", view_count=20),
    )
    session.commit()
    latest = get_latest_metrics_by_job_ids(session, ["job1"])
    assert latest["job1"].view_count == 20
    assert latest["job1"].snapshot_date == date(2026, 8, 11)
