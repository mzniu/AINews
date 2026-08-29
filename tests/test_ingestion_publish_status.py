"""Published-tag lookup for ingestion article lists."""
from __future__ import annotations

import pytest

from src.db.engine import init_db
from src.db.models.ingestion import IngestionSource
from src.db.models.publishing import PublishJob, PublisherAccount


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "publish_status.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    from src.db.engine import get_session_factory

    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="aitnt_news",
            enabled=True,
            schedule_cron="0 * * * *",
        )
    )
    session.add(
        PublisherAccount(
            id="acc1",
            platform="douyin",
            nickname="dy",
            session_path="data/publish/sessions/acc1.json",
            status="active",
        )
    )
    session.commit()
    yield session
    session.close()


def test_published_ingestion_ids_only_counts_published_jobs(db_session):
    from services.ingestion.publish_status import published_ingestion_ids

    db_session.add(
        PublishJob(
            id="job_pub",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="已发",
            status="published",
            source_type="ingestion",
            source_id="art_pub",
        )
    )
    db_session.add(
        PublishJob(
            id="job_pending",
            account_id="acc1",
            video_path="data/videos/b.mp4",
            title="排队",
            status="pending",
            source_type="ingestion",
            source_id="art_pending",
        )
    )
    db_session.add(
        PublishJob(
            id="job_index",
            account_id="acc1",
            video_path="data/videos/c.mp4",
            title="主页",
            status="published",
            source_type="index",
            source_id="art_pub",
        )
    )
    db_session.commit()

    found = published_ingestion_ids(db_session, ["art_pub", "art_pending", "art_plain"])
    assert found == {"art_pub"}
