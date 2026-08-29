"""Tests for TopHub hot radar fetch, match, and scoring integration."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.ingestion.article_scorer import score_article
from services.ingestion.hot_radar_service import (
    HotRadarMatch,
    _extract_items,
    _extract_tophub_items,
    match_article_hot_radar,
    parse_chinese_heat,
    refresh_hot_radar,
    seed_hot_radar_snapshot,
)
from services.ingestion.score_service import apply_score_to_article
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.utils.config import Config

SINA_FIXTURE_PATH = Config.ROOT_DIR / "tests" / "fixtures" / "sina" / "ai_hotlist.json"
TOPHUB_FIXTURE_PATH = Config.ROOT_DIR / "tests" / "fixtures" / "tophub" / "board_sample.json"


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    session = factory()
    source = IngestionSource(
        id="test_src",
        slug="test",
        display_name="Test",
        adapter_class="kr36_news",
        enabled=True,
    )
    session.add(source)
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
api_base_url: https://api.tophubdata.com
access_key: test-key
refresh_cron: "0 8 * * *"
max_age_minutes: 1440
title_match_threshold: 0.72
boards:
  - id: test_board
    hashid: testhashid01
    name: 测试平台
    display: AI榜
    enabled: true
scoring:
  unmatched: 2.0
  rank_1_3: 10.0
  rank_4_10: 8.5
  rank_11_20: 7.0
  rank_21_50: 5.5
bonuses:
  top3_points: 3
  top10_points: 1
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", cfg_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", tmp_path / "hot_radar.local.yaml")
    return cfg_path


def test_parse_chinese_heat():
    assert parse_chinese_heat("404万") == 4_040_000
    assert parse_chinese_heat("79万") == 790_000
    assert parse_chinese_heat("1.2亿") == 120_000_000


def test_extract_sina_items_from_fixture():
    payload = json.loads(SINA_FIXTURE_PATH.read_text(encoding="utf-8"))
    items = _extract_items(payload)
    assert len(items) >= 10
    assert items[0]["rank"] == 1


def test_extract_tophub_items_from_fixture():
    payload = json.loads(TOPHUB_FIXTURE_PATH.read_text(encoding="utf-8"))
    items = _extract_tophub_items(payload, hashid="testhashid01")
    assert len(items) == 2
    assert items[0]["title"] == "OpenAI 发布新模型"
    assert items[0]["heat_value"] == 790_000


def test_match_by_url(db_session, hot_radar_cfg):
    rows = _extract_tophub_items(json.loads(TOPHUB_FIXTURE_PATH.read_text(encoding="utf-8")), hashid="testhashid01")
    seed_hot_radar_snapshot(db_session, items=rows, board="testhashid01")

    first = rows[0]
    match = match_article_hot_radar(
        db_session,
        title="different title",
        url=first["url"],
    )
    assert match is not None
    assert match.rank == 1
    assert match.match_method == "url"
    assert match.board_id == "test_board"


def test_match_by_title(db_session, hot_radar_cfg):
    rows = _extract_tophub_items(json.loads(TOPHUB_FIXTURE_PATH.read_text(encoding="utf-8")), hashid="testhashid01")
    seed_hot_radar_snapshot(db_session, items=rows, board="testhashid01")

    target = rows[1]
    match = match_article_hot_radar(
        db_session,
        title=target["title"],
        url="https://example.com/unrelated",
    )
    assert match is not None
    assert match.rank == target["rank"]
    assert match.match_method == "title"


def test_hot_radar_dimension_boosts_score(hot_radar_cfg):
    cfg = {
        "profile": "flash_news",
        "weights": {
            "timeliness": 0.15,
            "prominence": 0.15,
            "event_tension": 0.20,
            "breakthrough": 0.10,
            "product_heat": 0.08,
            "hook": 0.12,
            "relevance": 0.12,
            "data_signal": 0.02,
            "creatability": 0.02,
            "hot_radar": 0.04,
        },
        "grades": {"S": 85, "A": 70, "B": 55, "C": 40},
        "hot_radar": {
            "scoring": {
                "unmatched": 2.0,
                "rank_1_3": 10.0,
                "rank_4_10": 8.5,
                "rank_11_20": 7.0,
                "rank_21_50": 5.5,
            },
            "bonuses": {"top3_points": 3, "top10_points": 1},
        },
    }
    base_kwargs = dict(
        title="OpenAI 发布新模型",
        summary="一次重要 AI 更新。",
        content_text="OpenAI 发布新模型，ChatGPT 能力升级。",
        published_at=datetime.utcnow() - timedelta(hours=6),
        image_count=3,
        config=cfg,
    )
    without = score_article(**base_kwargs, hot_radar_match=None)
    with_match = score_article(
        **base_kwargs,
        hot_radar_match=HotRadarMatch(
            rank=2,
            heat_label="79万",
            heat_value=790_000,
            hot_title="OpenAI 发布新模型",
            hot_url="https://example.com/a",
            match_method="title",
            board="testhashid01",
            source="tophub",
            board_id="test_board",
            board_name="测试平台",
            board_display="AI榜",
        ),
    )
    assert with_match.total > without.total
    hot_dim = next(d for d in with_match.dimensions if d.key == "hot_radar")
    assert hot_dim.score >= 8.5
    assert any(b["reason"] == "AI热榜Top3" for b in with_match.bonuses)


def test_refresh_hot_radar_uses_cache(db_session, hot_radar_cfg, monkeypatch):
    seed_hot_radar_snapshot(
        db_session,
        items=[{"rank": 1, "title": "cached", "url": "https://example.com/a", "heat_label": "10万"}],
        board="testhashid01",
        fetched_at=datetime.utcnow(),
    )

    def fail_fetch(**kwargs):
        raise RuntimeError("should not fetch")

    monkeypatch.setattr(
        "services.ingestion.hot_radar_service.fetch_tophub_board_items",
        fail_fetch,
    )
    result = refresh_hot_radar(db_session, force=False)
    assert result["status"] == "fresh"


def test_apply_score_includes_hot_radar(db_session, hot_radar_cfg, monkeypatch):
    rows = _extract_tophub_items(json.loads(TOPHUB_FIXTURE_PATH.read_text(encoding="utf-8")), hashid="testhashid01")
    seed_hot_radar_snapshot(db_session, items=rows, board="testhashid01")

    monkeypatch.setattr(
        "services.ingestion.score_service.ensure_fresh_hot_radar",
        lambda db, config=None: {"status": "fresh"},
    )

    article = IngestedArticle(
        source_id="test_src",
        canonical_url=rows[0]["url"],
        title=rows[0]["title"],
        summary="summary",
        content_text="OpenAI 相关内容",
    )
    db_session.add(article)
    db_session.commit()

    result = apply_score_to_article(db_session, article, use_llm=False)
    breakdown = result["score_breakdown"]
    assert "hot_radar" in breakdown
    assert breakdown["hot_radar"]["rank"] == 1
