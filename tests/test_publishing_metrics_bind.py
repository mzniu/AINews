"""Tests for manual post binding."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.query import bind_published_post
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models import publishing_metrics  # noqa: F401


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_bind_published_post_updates_ids_and_status():
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
            title="待绑定",
            status="published",
            platform_post_id="xhs_999",
            metrics_match_status="unmatched",
            published_at=datetime(2026, 8, 10, 12, 0, 0),
        )
    )
    session.commit()

    result = bind_published_post(
        session,
        job_id="job1",
        platform_post_id="real-note-42",
        platform_post_url="https://www.xiaohongshu.com/explore/real-note-42",
    )
    session.commit()
    job = session.get(PublishJob, "job1")
    assert result["job_id"] == "job1"
    assert job.platform_post_id == "real-note-42"
    assert job.platform_post_url.endswith("real-note-42")
    assert job.metrics_match_status == "manual_matched"
