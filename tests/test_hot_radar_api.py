"""Hot radar admin API tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.ingestion.hot_radar_service import seed_hot_radar_snapshot
from services.ingestion.registry import sync_sources_to_db
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource


def _load_hot_radar_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "hot_radar_routes.py"
    spec = importlib.util.spec_from_file_location("hot_radar_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_hot_radar_api.db"
    cfg_path = tmp_path / "hot_radar.yaml"
    cfg_path.write_text(
        """
enabled: true
provider: tophub
access_key: test-key
max_age_minutes: 1440
boards:
  - id: test_board
    hashid: testhashid01
    name: 测试平台
    display: AI榜
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", cfg_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", tmp_path / "hot_radar.local.yaml")
    init_db()
    with get_session_factory()() as session:
        sync_sources_to_db(session)
        source = IngestionSource(
            id="test_src",
            slug="test",
            display_name="Test",
            adapter_class="kr36_news",
            enabled=True,
        )
        session.merge(source)
        session.commit()
    app = FastAPI()
    app.include_router(_load_hot_radar_router(), prefix="/api/ingestion")
    return TestClient(app)


def test_get_hot_radar_empty(client):
    resp = client.get("/api/ingestion/hot-radar")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "empty"
    assert data["items"] == []


def test_get_hot_radar_with_snapshot(client):
    with get_session_factory()() as session:
        seed_hot_radar_snapshot(
            session,
            board="testhashid01",
            items=[
                {
                    "rank": 1,
                    "title": "OpenAI 发布新模型",
                    "url": "https://example.com/a",
                    "heat_label": "79万",
                    "heat_value": 790000,
                }
            ],
        )
    resp = client.get("/api/ingestion/hot-radar")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert len(data["items"]) == 1
    assert data["items"][0]["rank"] == 1
    assert len(data["boards"]) == 1


def test_get_article_hot_radar_match(client):
    with get_session_factory()() as session:
        seed_hot_radar_snapshot(
            session,
            board="testhashid01",
            items=[
                {
                    "rank": 2,
                    "title": "OpenAI 发布新模型",
                    "url": "https://example.com/a",
                    "heat_label": "79万",
                }
            ],
        )
        article = IngestedArticle(
            source_id="test_src",
            canonical_url="https://example.com/a",
            title="OpenAI 发布新模型",
            score_breakdown_json=json.dumps(
                {
                    "hot_radar": {
                        "rank": 2,
                        "heat_label": "79万",
                        "hot_title": "OpenAI 发布新模型",
                        "match_method": "url",
                    },
                    "dimensions": [
                        {
                            "key": "hot_radar",
                            "label": "热榜雷达",
                            "score": 8.5,
                            "weight": 0.04,
                            "weighted": 3.4,
                            "signals": ["测试平台·AI榜#2"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        )
        session.add(article)
        session.commit()
        article_id = article.id

    resp = client.get(f"/api/ingestion/hot-radar/articles/{article_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] is True
    assert data["match"]["rank"] == 2
    assert data["hot_radar_dimension"]["score"] == 8.5


def test_refresh_hot_radar_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.hot_radar_service.fetch_tophub_board_items",
        lambda **kwargs: [
            {
                "rank": 1,
                "title": "测试热榜",
                "url": "https://example.com/hot",
                "heat_label": "10万",
                "heat_value": 100000,
                "external_id": "testhashid01",
            }
        ],
    )
    resp = client.post("/api/ingestion/hot-radar/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "refreshed"

    list_resp = client.get("/api/ingestion/hot-radar")
    assert list_resp.json()["items"][0]["title"] == "测试热榜"


def test_get_hot_radar_discovery_queue(client):
    from datetime import datetime

    from src.db.models.ingestion import IngestionJob

    with get_session_factory()() as session:
        session.add(
            IngestionJob(
                job_type="hot_radar_discovery",
                source_id="test_src",
                status="pending",
                payload_json=json.dumps(
                    {
                        "url": "https://m.ithome.com/html/1.htm",
                        "title": "队列测试",
                        "source_id": "test_src",
                        "board_id": "test_board",
                        "rank": 2,
                        "heat_label": "5万",
                    },
                    ensure_ascii=False,
                ),
            )
        )
        session.commit()

    resp = client.get("/api/ingestion/hot-radar/discovery-queue")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["pending"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "队列测试"
    assert data["items"][0]["board_label"] == "测试平台·AI榜"


def test_hot_radar_settings_roundtrip(client):
    get_resp = client.get("/api/ingestion/hot-radar/settings")
    assert get_resp.status_code == 200
    assert get_resp.json()["has_access_key"] is True

    put_resp = client.put(
        "/api/ingestion/hot-radar/settings",
        json={
            "enabled": True,
            "refresh_cron": "0 9 * * *",
            "access_key": "new-secret-key",
            "boards": [
                {
                    "id": "test_board",
                    "hashid": "testhashid01",
                    "name": "测试平台",
                    "display": "AI榜",
                    "enabled": True,
                }
            ],
        },
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["refresh_cron"] == "0 9 * * *"
    assert data["access_key_masked"].startswith("new-")
