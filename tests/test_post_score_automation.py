"""Tests for post-score enqueue hook (legacy module name)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from services.ingestion.post_score_automation import maybe_run_post_score_automation
from services.ingestion.score_service import apply_score_to_article
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "post_score_auto.db"
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


@patch("services.ingestion.post_score_automation.maybe_enqueue_media_job")
def test_maybe_run_post_score_automation_enqueues(mock_enqueue, db_session):
    article = IngestedArticle(
        id="art1",
        source_id="src1",
        canonical_url="https://example.com/1",
        title="t",
        content_text="c",
        score_total=88.0,
    )
    db_session.add(article)
    db_session.flush()
    mock_enqueue.return_value = {"enqueued": True, "job_id": "j1"}
    result = maybe_run_post_score_automation(
        db_session, article, final_grade="S", final_total=88.0
    )
    assert result["enqueued"] is True
    mock_enqueue.assert_called_once()


@patch("services.ingestion.score_service.maybe_run_post_score_automation")
def test_apply_score_triggers_automation(mock_auto, db_session):
    article = IngestedArticle(
        id="art_auto",
        source_id="src1",
        canonical_url="https://example.com/auto",
        title="OpenAI 发布 GPT-5",
        summary="重磅",
        content_text="OpenAI 今日发布 GPT-5，参数突破万亿。",
        published_at=datetime.utcnow(),
    )
    db_session.add(article)
    db_session.flush()
    mock_auto.return_value = {"enqueued": True, "job_id": "j1"}

    with patch("services.ingestion.score_service.score_article") as mock_score:
        from services.ingestion.article_scorer import ArticleScoreResult

        mock_score.return_value = ArticleScoreResult(
            profile="flash_news",
            total=88.0,
            grade="S",
            dimensions=[],
            bonuses=[],
            penalties=[],
            recommendation="立即出快讯",
        )
        result = apply_score_to_article(db_session, article, use_llm=False)

    mock_auto.assert_called_once()
    assert result["score_grade"] == "S"
