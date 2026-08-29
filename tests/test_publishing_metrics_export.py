"""Tests for metrics CSV export."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.export import build_published_posts_csv
from services.publishing.metrics.snapshot_store import upsert_metric_snapshot
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models import publishing_metrics  # noqa: F401


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_build_published_posts_csv_includes_headers_and_row():
    session = _session()
    session.add(
        PublisherAccount(
            id="acc1",
            platform="xiaohongshu",
            nickname="测试号",
            platform_uid="uid1",
            session_path="data/publish/sessions/acc1.enc",
        )
    )
    session.flush()
    session.add(
        PublishJob(
            id="job1",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="导出测试",
            status="published",
            platform_post_id="note1",
            published_at=datetime(2026, 8, 10, 12, 0, 0),
        )
    )
    session.flush()
    upsert_metric_snapshot(
        session,
        job_id="job1",
        account_id="acc1",
        platform="xiaohongshu",
        snapshot_date=datetime(2026, 8, 11).date(),
        metrics=PostMetricsItem(platform_post_id="note1", view_count=200, like_count=10),
    )
    session.commit()

    csv_text = build_published_posts_csv(session, days=30)
    assert "标题" in csv_text
    assert "导出测试" in csv_text
    assert "200" in csv_text
    assert "note1" in csv_text
    assert "关注" in csv_text
    assert "3秒播放率" in csv_text
    assert "完播率" in csv_text
