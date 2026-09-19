"""Tests for expanded hot radar URL discovery."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from services.ingestion.hot_radar_discovery import (
    enqueue_hot_url_discoveries,
    is_url_blocked,
    resolve_source_for_url,
    select_discovery_candidates,
)
from services.ingestion.hot_radar_service import seed_hot_radar_snapshot
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestionJob, IngestionSource


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    session = get_session_factory()()
    for sid, adapter in [
        ("ithome_it", "ithome_news"),
        ("kr36_ai", "kr36_news"),
        ("readhub_ai", "readhub_news"),
        ("aibase_daily", "aibase_news"),
        ("ifeng_ai", "ifeng_news"),
        ("sina_tech", "sina_tech_news"),
    ]:
        session.add(
            IngestionSource(
                id=sid,
                slug=sid,
                display_name=sid,
                adapter_class=adapter,
                enabled=True,
            )
        )
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def discovery_cfg(tmp_path, monkeypatch):
    cfg_path = tmp_path / "hot_radar.yaml"
    cfg_path.write_text(
        """
enabled: true
boards:
  - id: board_a
    hashid: hashboardaaa01
    name: 测试A
    display: AI
    enabled: true
  - id: board_b
    hashid: hashboardbbb02
    name: 测试B
    display: AI
    enabled: true
discovery:
  enabled: true
  max_rank: 10
  max_urls_per_refresh: 4
  per_board_max: 2
  domain_source_map:
    ithome.com: ithome_it
    36kr.com: kr36_ai
    readhub.cn: readhub_ai
    aibase.com: aibase_daily
    ifeng.com: ifeng_ai
    sina.cn: sina_tech
  blocked_domains:
    - weibo.com
    - zhihu.com
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", cfg_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", tmp_path / "hot_radar.local.yaml")
    monkeypatch.setenv("AINEWS_DISABLE_EFFECTIVE_CONFIG", "1")
    return cfg_path


def test_resolve_source_for_url_new_domains(discovery_cfg):
    assert resolve_source_for_url("https://readhub.cn/topic/abc") == "readhub_ai"
    assert resolve_source_for_url("https://www.aibase.com/zh/news/1") == "aibase_daily"
    assert resolve_source_for_url("https://tech.ifeng.com/c/abc") == "ifeng_ai"
    assert resolve_source_for_url("https://tech.sina.cn/2026/detail.html") == "sina_tech"
    assert resolve_source_for_url("https://k.sina.cn/article_123.html") == "sina_tech"


def test_is_url_blocked_skips_social_domains(discovery_cfg):
    assert is_url_blocked("https://weibo.com/hot/1") is True
    assert is_url_blocked("https://www.zhihu.com/question/1") is True
    assert is_url_blocked("https://tech.sina.cn/detail.html") is False


def test_select_discovery_candidates_per_board_cap(discovery_cfg):
    candidates = [
        {"board_id": "board_a", "rank": 1, "url": "https://m.ithome.com/1"},
        {"board_id": "board_a", "rank": 2, "url": "https://m.ithome.com/2"},
        {"board_id": "board_a", "rank": 3, "url": "https://m.ithome.com/3"},
        {"board_id": "board_b", "rank": 1, "url": "https://www.36kr.com/p/1"},
        {"board_id": "board_b", "rank": 2, "url": "https://www.36kr.com/p/2"},
        {"board_id": "board_b", "rank": 3, "url": "https://www.36kr.com/p/3"},
    ]
    selected = select_discovery_candidates(
        candidates,
        per_board_max=2,
        max_urls_per_refresh=4,
    )
    assert len(selected) == 4
    assert sum(1 for row in selected if row["board_id"] == "board_a") == 2
    assert sum(1 for row in selected if row["board_id"] == "board_b") == 2


def test_enqueue_skips_blocked_and_unknown(db_session, discovery_cfg):
    seed_hot_radar_snapshot(
        db_session,
        board="hashboardaaa01",
        fetched_at=datetime.utcnow(),
        items=[
            {"rank": 1, "title": "A", "url": "https://m.ithome.com/html/1.htm"},
            {"rank": 2, "title": "B", "url": "https://weibo.com/hot/1"},
            {"rank": 3, "title": "C", "url": "https://unknown.example.com/c"},
        ],
    )
    result = enqueue_hot_url_discoveries(db_session)
    assert result["enqueued"] == 1
    assert result["skipped"] >= 2
    job = db_session.query(IngestionJob).one()
    payload = json.loads(job.payload_json)
    assert payload["ingest_origin"] == "hot_radar_discovery"
    assert payload["board_id"] == "board_a"
    assert payload["rank"] == 1


def test_enqueue_per_board_limits(db_session, discovery_cfg):
    seed_hot_radar_snapshot(
        db_session,
        board="hashboardaaa01",
        fetched_at=datetime.utcnow(),
        items=[
            {"rank": i, "title": f"A{i}", "url": f"https://m.ithome.com/html/{i}.htm"}
            for i in range(1, 6)
        ],
    )
    seed_hot_radar_snapshot(
        db_session,
        board="hashboardbbb02",
        fetched_at=datetime.utcnow(),
        items=[
            {"rank": i, "title": f"B{i}", "url": f"https://www.36kr.com/p/{i}"}
            for i in range(1, 6)
        ],
    )
    result = enqueue_hot_url_discoveries(db_session)
    assert result["enqueued"] == 4
    jobs = db_session.query(IngestionJob).all()
    assert len(jobs) == 4
