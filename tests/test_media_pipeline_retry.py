"""Tests for manual media pipeline retry options."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.ingestion.media_job_service import enqueue_media_job
from services.ingestion.media_pipeline_trigger import build_manual_media_retry_config
from src.db.engine import Base
from src.db.models.ingestion import IngestedArticle, IngestionSource


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "media_retry.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        IngestionSource(
            id="src1",
            slug="test",
            display_name="Test",
            adapter_class="test",
            enabled=True,
        )
    )
    session.add(
        IngestedArticle(
            id="art1",
            source_id="src1",
            canonical_url="https://example.com/a1",
            title="测试出片",
            score_grade="S",
            score_total=90.0,
            video_draft_json=json.dumps({"main_line1": "标题"}),
            generated_video_path="data/videos/old.mp4",
            media_pipeline_status="succeeded",
        )
    )
    session.commit()
    yield session
    session.close()


def test_build_manual_media_retry_config():
    cfg = build_manual_media_retry_config(include_story_images=True, has_video_draft=True)
    assert cfg["include_story_images"] is True
    assert cfg["force_score_images"] is False
    assert cfg["select_top_by_rank"] is True
    assert cfg["generate_content"] is False

    cfg_rescore = build_manual_media_retry_config(
        include_story_images=True, has_video_draft=True, force_score_images=True
    )
    assert cfg_rescore["include_story_images"] is True
    assert cfg_rescore["force_score_images"] is True
    assert cfg_rescore["select_top_by_rank"] is True

    cfg2 = build_manual_media_retry_config(include_story_images=False, has_video_draft=False)
    assert cfg2["include_story_images"] is False
    assert cfg2["force_score_images"] is False
    assert cfg2["generate_content"] is True


def test_enqueue_media_job_stores_pipeline_config(db_session):
    overrides = build_manual_media_retry_config(include_story_images=True, has_video_draft=True)
    job = enqueue_media_job(
        db_session,
        "art1",
        trigger_reason="manual_retry",
        final_grade="S",
        final_total=90.0,
        pipeline_config=overrides,
        force=True,
    )
    assert job is not None
    payload = json.loads(job.payload_json)
    assert payload["pipeline_config"]["select_top_by_rank"] is True
