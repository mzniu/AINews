"""Tests for AI-enhanced story clustering."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.ingestion.story_cluster_config import load_story_cluster_config
from services.ingestion.story_cluster_embedding import embedding_similarity, hashing_embedding
from services.ingestion.story_cluster_scoring import evaluate_pair_match
from src.db.engine import Base
from src.db.models.ingestion import IngestedArticle, IngestionSource


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="aitnt_news",
            config_json="{}",
        )
    )
    db.commit()
    yield db
    db.close()


def _article(session, *, title: str, summary: str = "", content: str = "", suffix: str = "1"):
    row = IngestedArticle(
        source_id="src1",
        canonical_url=f"http://example.com/{suffix}",
        title=title,
        summary=summary,
        content_text=content or summary,
        published_at=datetime.utcnow(),
        status="fetched",
    )
    session.add(row)
    session.flush()
    return row


def test_load_story_cluster_config_has_ai_sections():
    cfg = load_story_cluster_config()
    assert "embedding" in cfg
    assert "llm" in cfg
    assert "review" in cfg
    assert cfg["embedding"]["enabled"] is True


def test_hashing_embedding_is_deterministic():
    left = hashing_embedding("OpenAI 发布 GPT-5")
    right = hashing_embedding("OpenAI 发布 GPT-5")
    assert left == right


def test_embedding_similarity_higher_for_related_titles(session):
    left = _article(
        session,
        title="OpenAI 发布 GPT-5 多模态模型",
        content="OpenAI 今日正式发布 GPT-5，支持多模态能力。",
        suffix="a",
    )
    right = _article(
        session,
        title="GPT-5来了：OpenAI多模态大模型正式发布",
        content="OpenAI 正式发布 GPT-5，具备多模态能力，引发行业关注。",
        suffix="b",
    )
    unrelated = _article(
        session,
        title="某车企宣布降价促销",
        content="某车企宣布全系降价，与 AI 无关。",
        suffix="c",
    )
    related_score = embedding_similarity(left, right, config=load_story_cluster_config())
    unrelated_score = embedding_similarity(left, unrelated, config=load_story_cluster_config())
    assert related_score > unrelated_score


def test_evaluate_pair_match_clear_pass_without_llm(session):
    left = _article(
        session,
        title="OpenAI 发布 GPT-5 旅游行业应用",
        summary="OpenAI GPT-5 旅游",
        suffix="a",
    )
    right = _article(
        session,
        title="OpenAI发布GPT-5旅游行业应用详解",
        summary="OpenAI GPT-5 旅游",
        suffix="b",
    )
    cfg = load_story_cluster_config()
    cfg["llm"] = {"enabled": False}
    cfg["embedding"] = {"enabled": False}
    result = evaluate_pair_match(left, right, config=cfg)
    assert result.should_match is True
    assert result.cluster_method == "rule"


@patch("services.ingestion.story_cluster_scoring.adjudicate_same_story")
def test_evaluate_pair_match_gray_zone_uses_llm(mock_llm, session):
    mock_llm.return_value = {"same_story": True, "confidence": 0.91, "reason": "同一事件"}
    left = _article(session, title="OpenAI 发布 GPT-5", suffix="a")
    right = _article(session, title="谷歌发布 Gemini 2", suffix="b")
    cfg = load_story_cluster_config()
    cfg["title_threshold"] = 0.95
    cfg["gray_low"] = 0.1
    cfg["embedding"] = {"enabled": True, "rule_weight": 0.5, "embedding_weight": 0.5}
    cfg["llm"] = {"enabled": True, "min_confidence": 0.7}
    result = evaluate_pair_match(left, right, config=cfg)
    assert result.should_match is True
    assert result.cluster_method == "rule+embedding+llm"
    mock_llm.assert_called_once()
