"""Tests for metrics sync orchestrator (no browser)."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.sync_orchestrator import MetricsSyncOrchestrator
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models import publishing_metrics  # noqa: F401


def _factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_sync_account_applies_fuzzy_match_and_snapshot(monkeypatch):
    factory = _factory()
    published_at = datetime.utcnow() - timedelta(days=1)
    with factory() as session:
        session.add(
            PublisherAccount(
                id="acc1",
                platform="xiaohongshu",
                nickname="测试号",
                platform_uid="uid1",
                session_path="data/publish/sessions/acc1.enc",
                status="active",
            )
        )
        session.add(
            PublishJob(
                id="job1",
                account_id="acc1",
                video_path="data/videos/a.mp4",
                title="AI新闻速递",
                status="published",
                platform_post_id="xhs_123",
                published_at=published_at,
            )
        )
        session.commit()

    items = [
        PostMetricsItem(
            platform_post_id="real-note-99",
            title="AI新闻速递",
            published_at=published_at + timedelta(hours=2),
            view_count=500,
            like_count=20,
        )
    ]

    fetch_mock = MagicMock(return_value=items)
    monkeypatch.setattr(
        "services.publishing.metrics.sync_orchestrator.fetch_platform_metrics_items",
        fetch_mock,
    )

    orchestrator = MetricsSyncOrchestrator(factory)
    result = orchestrator.sync_account("acc1", snapshot_date=None)

    assert result.posts_synced == 1
    assert result.posts_unmatched == 0

    with factory() as session:
        job = session.get(PublishJob, "job1")
        assert job.platform_post_id == "real-note-99"
        assert job.metrics_match_status == "fuzzy_matched"
        assert job.metrics_last_synced_at is not None
        assert job.platform_post_url == "https://www.xiaohongshu.com/explore/real-note-99"


def test_sync_account_refreshes_matched_job_by_stored_url(monkeypatch):
    factory = _factory()
    published_at = datetime.utcnow() - timedelta(days=1)
    with factory() as session:
        session.add(
            PublisherAccount(
                id="acc1",
                platform="douyin",
                nickname="测试号",
                platform_uid="uid1",
                session_path="data/publish/sessions/acc1.enc",
                status="active",
            )
        )
        session.add(
            PublishJob(
                id="job1",
                account_id="acc1",
                video_path="data/videos/a.mp4",
                title="旧标题",
                status="published",
                platform_post_id="7123456789012345678",
                platform_post_url="https://www.douyin.com/video/7123456789012345678",
                metrics_match_status="matched",
                published_at=published_at,
            )
        )
        session.commit()

    items = [
        PostMetricsItem(
            platform_post_id="7123456789012345678",
            title="平台改过的标题",
            published_at=published_at,
            view_count=999,
            like_count=12,
            post_url="https://www.douyin.com/video/7123456789012345678",
        )
    ]
    fetch_mock = MagicMock(return_value=items)
    monkeypatch.setattr(
        "services.publishing.metrics.sync_orchestrator.fetch_platform_metrics_items",
        fetch_mock,
    )

    orchestrator = MetricsSyncOrchestrator(factory)
    result = orchestrator.sync_account("acc1")

    assert result.posts_synced == 1
    assert fetch_mock.call_args.kwargs.get("needed_post_ids") == {"7123456789012345678"}

    with factory() as session:
        job = session.get(PublishJob, "job1")
        assert job.metrics_match_status == "matched"
        assert job.platform_post_url == "https://www.douyin.com/video/7123456789012345678"


def test_sync_account_fetches_bound_job_missing_from_list(monkeypatch):
    factory = _factory()
    published_at = datetime.utcnow() - timedelta(days=2)
    with factory() as session:
        session.add(
            PublisherAccount(
                id="acc1",
                platform="douyin",
                nickname="测试号",
                platform_uid="uid1",
                session_path="data/publish/sessions/acc1.enc",
                status="active",
            )
        )
        session.add(
            PublishJob(
                id="job1",
                account_id="acc1",
                video_path="data/videos/a.mp4",
                title="已绑定作品",
                status="published",
                platform_post_id="7123456789012345678",
                platform_post_url="https://www.douyin.com/video/7123456789012345678",
                metrics_match_status="matched",
                published_at=published_at,
            )
        )
        session.commit()

    list_item = PostMetricsItem(
        platform_post_id="other-video",
        title="另一条",
        published_at=published_at,
        view_count=1,
    )
    detail_item = PostMetricsItem(
        platform_post_id="7123456789012345678",
        title="已绑定作品",
        published_at=published_at,
        view_count=321,
        post_url="https://www.douyin.com/video/7123456789012345678",
    )
    monkeypatch.setattr(
        "services.publishing.metrics.sync_orchestrator.fetch_platform_metrics_items",
        MagicMock(return_value=[list_item]),
    )
    detail_mock = MagicMock(return_value=detail_item)
    monkeypatch.setattr(
        "services.publishing.metrics.sync_orchestrator.fetch_platform_post_metrics",
        detail_mock,
    )

    orchestrator = MetricsSyncOrchestrator(factory)
    result = orchestrator.sync_account("acc1")

    assert result.posts_synced == 1
    detail_mock.assert_called_once()
    assert detail_mock.call_args.kwargs["platform_post_id"] == "7123456789012345678"
    assert "douyin.com/video/7123456789012345678" in detail_mock.call_args.kwargs["post_url"]

    with factory() as session:
        job = session.get(PublishJob, "job1")
        assert job.metrics_match_status == "matched"
        assert job.metrics_last_synced_at is not None


def test_sync_account_keeps_bound_status_when_list_empty(monkeypatch):
    factory = _factory()
    published_at = datetime.utcnow() - timedelta(days=1)
    with factory() as session:
        session.add(
            PublisherAccount(
                id="acc1",
                platform="douyin",
                nickname="测试号",
                platform_uid="uid1",
                session_path="data/publish/sessions/acc1.enc",
                status="active",
            )
        )
        session.add(
            PublishJob(
                id="job1",
                account_id="acc1",
                video_path="data/videos/a.mp4",
                title="已绑定作品",
                status="published",
                platform_post_id="7123456789012345678",
                platform_post_url="https://www.douyin.com/video/7123456789012345678",
                metrics_match_status="matched",
                published_at=published_at,
            )
        )
        session.commit()

    monkeypatch.setattr(
        "services.publishing.metrics.sync_orchestrator.fetch_platform_metrics_items",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "services.publishing.metrics.sync_orchestrator.fetch_platform_post_metrics",
        MagicMock(return_value=None),
    )

    orchestrator = MetricsSyncOrchestrator(factory)
    result = orchestrator.sync_account("acc1")

    assert result.posts_synced == 0
    assert result.posts_unmatched == 1

    with factory() as session:
        job = session.get(PublishJob, "job1")
        assert job.metrics_match_status == "matched"
        assert job.platform_post_url == "https://www.douyin.com/video/7123456789012345678"
