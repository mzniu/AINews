from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.mature_metrics import (
    get_mature_platform_metrics,
    get_pending_queue_stats,
)
from services.publishing.metrics.snapshot_store import upsert_metric_snapshot
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models.publishing_metrics import PublishPostMetricSnapshot
from src.db.models import ingestion  # noqa: F401
from src.db.models import publishing_metrics  # noqa: F401
from src.db.models import publishing  # noqa: F401


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _snapshot(
    session,
    *,
    job_id: str,
    account_id: str,
    platform: str,
    snapshot_date,
    view_count: int,
    completion_rate: float,
    fetched_at: datetime,
    platform_post_id: str,
) -> None:
    upsert_metric_snapshot(
        session,
        job_id=job_id,
        account_id=account_id,
        platform=platform,
        snapshot_date=snapshot_date,
        metrics=PostMetricsItem(
            platform_post_id=platform_post_id,
            view_count=view_count,
            completion_rate=completion_rate,
        ),
    )
    row = (
        session.query(PublishPostMetricSnapshot)
        .filter_by(job_id=job_id, snapshot_date=snapshot_date)
        .one()
    )
    row.fetched_at = fetched_at


def test_mature_metrics_require_fetched_after_horizon_and_use_first_qualifying_snapshot():
    session = _session()
    published = datetime(2026, 9, 10, 0, 0, 0)
    session.add(
        PublisherAccount(
            id="acc-wc",
            platform="wechat_channels",
            nickname="视频号",
            platform_uid="wc1",
            session_path="data/publish/sessions/acc-wc.enc",
        )
    )
    session.add(
        PublishJob(
            id="job-mature",
            account_id="acc-wc",
            video_path="data/videos/a.mp4",
            title="成熟样本",
            status="published",
            published_at=published,
        )
    )
    session.add(
        PublishJob(
            id="job-young",
            account_id="acc-wc",
            video_path="data/videos/b.mp4",
            title="未成熟",
            status="published",
            published_at=published,
        )
    )
    session.flush()

    _snapshot(
        session,
        job_id="job-mature",
        account_id="acc-wc",
        platform="wechat_channels",
        snapshot_date=published.date(),
        view_count=500,
        completion_rate=0.20,
        fetched_at=published + timedelta(hours=12),
        platform_post_id="p1",
    )
    _snapshot(
        session,
        job_id="job-mature",
        account_id="acc-wc",
        platform="wechat_channels",
        snapshot_date=(published + timedelta(days=1)).date(),
        view_count=1400,
        completion_rate=0.40,
        fetched_at=published + timedelta(hours=25),
        platform_post_id="p1",
    )
    _snapshot(
        session,
        job_id="job-mature",
        account_id="acc-wc",
        platform="wechat_channels",
        snapshot_date=(published + timedelta(days=2)).date(),
        view_count=9000,
        completion_rate=0.50,
        fetched_at=published + timedelta(hours=50),
        platform_post_id="p1",
    )
    _snapshot(
        session,
        job_id="job-young",
        account_id="acc-wc",
        platform="wechat_channels",
        snapshot_date=published.date(),
        view_count=50,
        completion_rate=0.10,
        fetched_at=published + timedelta(hours=10),
        platform_post_id="p2",
    )
    session.commit()

    metrics = get_mature_platform_metrics(
        session,
        platforms=["wechat_channels"],
        horizons=(24,),
        published_after=published - timedelta(days=1),
        published_before=published + timedelta(days=1),
    )
    row = metrics["wechat_channels"]["24h"]
    assert row["sample_size"] == 1
    assert row["median_views"] == 1400
    assert row["completion_rate"] == pytest.approx(0.40)


def test_pending_queue_stats_report_oldest_age_days():
    session = _session()
    now = datetime(2026, 9, 13, 8, 0, 0)
    session.add(
        PublisherAccount(
            id="acc-dy",
            platform="douyin",
            nickname="抖音",
            platform_uid="dy1",
            session_path="data/publish/sessions/acc-dy.enc",
        )
    )
    session.flush()
    session.add(
        PublishJob(
            id="job-old",
            account_id="acc-dy",
            video_path="data/videos/old.mp4",
            title="old",
            status="pending",
            created_at=now - timedelta(days=3),
            scheduled_at=now - timedelta(days=2, hours=12),
        )
    )
    session.add(
        PublishJob(
            id="job-new",
            account_id="acc-dy",
            video_path="data/videos/new.mp4",
            title="new",
            status="pending",
            created_at=now - timedelta(hours=1),
            scheduled_at=now + timedelta(hours=2),
        )
    )
    session.commit()

    stats = get_pending_queue_stats(session, now=now)
    assert stats["job_count"] == 2
    assert stats["unique_video_count"] == 2
    assert stats["oldest_age_days"] == pytest.approx(2.5, abs=1e-6)
