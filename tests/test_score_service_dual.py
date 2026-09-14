"""Tests for dual-dimension score breakdown in score_service (Phase 1a)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.ingestion.score_service import apply_score_to_article
from src.db.models.ingestion import IngestedArticle


def _article(**overrides) -> IngestedArticle:
    data = {
        "id": "art-phase1a-001",
        "source_id": "kr36_ai",
        "title": "突发？Meta核心研究员离职",
        "summary": "Meta AI 核心研究员宣布离职创业。",
        "content_text": "Meta 核心 AI 研究员离职创业。",
        "keywords_json": json.dumps(["AI", "Meta"]),
        "published_at": datetime.utcnow() - timedelta(hours=3),
        "view_count": 8000,
        "story_id": None,
    }
    data.update(overrides)
    return IngestedArticle(**data)


@patch("services.ingestion.score_service.maybe_run_post_score_automation", return_value={})
@patch("services.ingestion.score_service.match_article_hot_radar", return_value=None)
@patch("services.ingestion.score_service.ensure_fresh_hot_radar")
def test_apply_score_persists_dual_breakdown(mock_ensure, mock_match, mock_auto):
    db = MagicMock()
    db.query.return_value.filter_by.return_value.count.return_value = 3
    article = _article()

    result = apply_score_to_article(db, article, use_llm=False)

    breakdown = json.loads(article.score_breakdown_json)
    assert "industry" in breakdown
    assert "viral" in breakdown
    assert breakdown["industry"]["grade"] == article.score_grade
    assert breakdown["viral"]["total"] is not None
    assert breakdown["final"]["publish_tier"] in {
        "viral_priority",
        "industry_priority",
        "standard",
        "skip",
    }
    assert breakdown["final"]["industry_grade"] == article.score_grade
    assert breakdown["final"]["viral_grade"] == breakdown["viral"]["grade"]
    # backward compat
    assert breakdown["total"] == breakdown["industry"]["total"]
    assert breakdown["grade"] == breakdown["industry"]["grade"]
    assert "dimensions" in breakdown
    assert result["score_breakdown"]["viral"]["grade"] == breakdown["viral"]["grade"]
