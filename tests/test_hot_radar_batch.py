"""Tests for hot radar batch matching, scoring factors, inheritance, discovery."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from services.ingestion.hot_radar_batch import (
    apply_story_inheritance,
    batch_match_hot_radar,
    get_persisted_match,
    match_candidate_to_hot_radar_match,
)
from services.ingestion.hot_radar_matching import compute_final_confidence, compute_time_factor
from services.ingestion.hot_radar_service import seed_hot_radar_snapshot
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import HotRadarArticleMatch, IngestedArticle, IngestionSource, Story, StoryArticle


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="ithome_it",
            slug="ithome_it",
            display_name="IT之家",
            adapter_class="ithome_news",
            enabled=True,
        )
    )
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def hot_radar_cfg(tmp_path, monkeypatch):
    cfg_path = tmp_path / "hot_radar.yaml"
    cfg_path.write_text(
        """
enabled: true
provider: tophub
access_key: test-key
boards:
  - id: test_board
    hashid: testhashid01
    name: 测试平台
    display: AI榜
    enabled: true
    weight: 1.0
matching:
  min_confidence: 0.6
  title_similarity_threshold: 0.72
  time_window_hours: 48
  use_embedding_in_gray: false
batch:
  rescore_days: 30
  rescore_on_refresh: false
discovery:
  enabled: false
inheritance:
  enabled: true
  confidence_factor: 0.85
  rank_penalty: 3
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", cfg_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", tmp_path / "hot_radar.local.yaml")
    monkeypatch.setenv("AINEWS_DISABLE_EFFECTIVE_CONFIG", "1")
    return cfg_path


def test_batch_match_persists_url_match(db_session, hot_radar_cfg):
    snapshot = seed_hot_radar_snapshot(
        db_session,
        board="testhashid01",
        items=[
            {
                "rank": 2,
                "title": "OpenAI 发布新模型",
                "url": "https://m.ithome.com/html/992565.htm",
                "heat_label": "79万",
            }
        ],
    )
    article = IngestedArticle(
        source_id="ithome_it",
        canonical_url="https://www.ithome.com/0/992/565.htm",
        title="OpenAI 发布新模型，性能大幅提升",
        published_at=datetime.utcnow() - timedelta(hours=6),
    )
    db_session.add(article)
    db_session.commit()

    result = batch_match_hot_radar(db_session)
    assert result["matched_articles"] >= 1

    match = get_persisted_match(db_session, article.id)
    assert match is not None
    assert match.rank == 2
    assert match.match_method.startswith("url")
    assert match.confidence >= 0.6

    row = db_session.query(HotRadarArticleMatch).filter_by(article_id=article.id).one()
    assert row.snapshot_id == snapshot.id


def test_compute_time_factor_decays_outside_window():
    cfg = {"time_window_hours": 24, "time_decay_per_day": 0.2, "time_factor_floor": 0.6}
    now = datetime.utcnow()
    factor = compute_time_factor(
        article_published_at=now - timedelta(hours=72),
        snapshot_fetched_at=now,
        config=cfg,
    )
    assert factor < 1.0
    assert factor >= 0.6


def test_board_weight_reduces_confidence(hot_radar_cfg):
    cfg = {"matching": {"min_confidence": 0.6}}
    low = compute_final_confidence(0.9, board_weight=0.5, time_factor=1.0)
    high = compute_final_confidence(0.9, board_weight=1.0, time_factor=1.0)
    assert low < high


def test_story_inheritance_grants_match_to_cluster_peer(db_session, hot_radar_cfg):
    snapshot = seed_hot_radar_snapshot(
        db_session,
        board="testhashid01",
        items=[
            {
                "rank": 1,
                "title": "OpenAI 发布新模型",
                "url": "https://example.com/a",
                "heat_label": "10万",
            }
        ],
    )
    story = Story(canonical_title="OpenAI 发布新模型")
    db_session.add(story)
    db_session.flush()

    matched_article = IngestedArticle(
        source_id="ithome_it",
        canonical_url="https://example.com/a",
        title="OpenAI 发布新模型",
        story_id=story.id,
    )
    peer_article = IngestedArticle(
        source_id="ithome_it",
        canonical_url="https://example.com/b",
        title="行业评述：大模型竞争进入新阶段",
        story_id=story.id,
    )
    db_session.add_all([matched_article, peer_article])
    db_session.commit()

    batch_match_hot_radar(db_session)
    inherited = apply_story_inheritance(db_session)
    assert inherited >= 1

    peer_match = get_persisted_match(db_session, peer_article.id)
    assert peer_match is not None
    assert peer_match.match_method == "story_inherit"
    assert peer_match.inherited_from_article_id == matched_article.id


def test_match_candidate_to_hot_radar_match_exposes_effective_rank():
    from services.ingestion.hot_radar_batch import MatchCandidate

    candidate = MatchCandidate(
        rank=2,
        effective_rank=7,
        confidence=0.75,
        heat_label="79万",
        heat_value=790000,
        hot_title="title",
        hot_url="https://example.com",
        match_method="title_similarity",
        board="hash",
        board_id="bid",
        board_name="平台",
        board_display="AI",
        snapshot_id="snap-test",
    )
    match = match_candidate_to_hot_radar_match(candidate)
    assert match.rank == 7
    assert match.confidence == 0.75
