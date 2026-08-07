"""Tests for enqueue hook from score service."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from services.ingestion.media_job_service import maybe_enqueue_media_job
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "enqueue_hook.db"
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
    yield session
    session.close()


def test_maybe_enqueue_on_s_grade(db_session):
    article = IngestedArticle(
        id="a1",
        source_id="src1",
        canonical_url="https://example.com/1",
        title="t",
        content_text="c",
    )
    db_session.add(article)
    db_session.flush()
    result = maybe_enqueue_media_job(db_session, article, final_grade="S", final_total=88.0)
    assert result.get("enqueued") is True
    assert result.get("job_id")


def test_maybe_enqueue_on_score_80(db_session):
    article = IngestedArticle(
        id="a2",
        source_id="src1",
        canonical_url="https://example.com/2",
        title="t",
        content_text="c",
    )
    db_session.add(article)
    db_session.flush()
    result = maybe_enqueue_media_job(db_session, article, final_grade="A", final_total=81.0)
    assert result.get("enqueued") is True


def test_maybe_enqueue_skips_low_score(db_session):
    article = IngestedArticle(
        id="a3",
        source_id="src1",
        canonical_url="https://example.com/3",
        title="t",
        content_text="c",
    )
    db_session.add(article)
    db_session.flush()
    result = maybe_enqueue_media_job(db_session, article, final_grade="A", final_total=72.0)
    assert result.get("skipped") is True
