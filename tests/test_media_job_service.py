"""Tests for media generation job enqueue and claim."""
from __future__ import annotations

from datetime import datetime

import pytest

from services.ingestion.media_job_service import (
    claim_next_media_job,
    enqueue_media_job,
    has_active_media_job,
)
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource, MediaGenerationJob


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "media_job.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    session = factory()
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
    session.commit()
    article = IngestedArticle(
        id="art1",
        source_id="src1",
        canonical_url="https://example.com/1",
        title="Test",
        content_text="body",
    )
    session.add(article)
    session.commit()
    yield session
    session.close()


def test_enqueue_creates_pending_job(db_session):
    job = enqueue_media_job(
        db_session,
        "art1",
        trigger_reason="grade=S,score=88",
        final_grade="S",
        final_total=88.0,
    )
    assert job.id
    assert job.status == "pending"
    assert job.article_id == "art1"
    assert has_active_media_job(db_session, "art1") is True


def test_enqueue_skips_if_pending_exists(db_session):
    enqueue_media_job(db_session, "art1", trigger_reason="x", final_grade="S", final_total=90.0)
    second = enqueue_media_job(db_session, "art1", trigger_reason="y", final_grade="S", final_total=91.0)
    assert second is None
    count = db_session.query(MediaGenerationJob).filter_by(article_id="art1").count()
    assert count == 1


def test_enqueue_skips_if_pipeline_already_succeeded(db_session):
    article = db_session.get(IngestedArticle, "art1")
    article.media_pipeline_status = "succeeded"
    article.generated_video_path = "/data/videos/done.mp4"
    article.generated_video_at = datetime.utcnow()
    db_session.flush()
    job = enqueue_media_job(db_session, "art1", trigger_reason="x", final_grade="S", final_total=90.0)
    assert job is None


def test_claim_next_media_job(db_session):
    enqueue_media_job(db_session, "art1", trigger_reason="x", final_grade="S", final_total=90.0)
    claimed = claim_next_media_job(db_session)
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.started_at is not None
