"""API tests for image relevance scoring endpoint."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from src.db.engine import init_db, get_session_factory
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionSource


def _load_ingestion_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "ingestion_routes.py"
    spec = importlib.util.spec_from_file_location("ingestion_routes_img", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_img_api.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    with get_session_factory()() as session:
        session.add(
            IngestionSource(
                id="test_src",
                slug="test",
                display_name="Test",
                adapter_class="test",
                enabled=True,
            )
        )
        session.flush()
        session.add(
            IngestedArticle(
                id="art_api",
                source_id="test_src",
                canonical_url="https://example.com/api",
                title="API 测试文章",
                summary="摘要",
            )
        )
        img_path = tmp_path / "api_img.jpg"
        Image.new("RGB", (800, 600), color="green").save(img_path)
        session.add(
            ArticleImage(
                id="img_api",
                article_id="art_api",
                original_url="https://cdn.example.com/api.jpg",
                local_path=str(img_path),
                sort_order=0,
                download_status="ok",
            )
        )
        session.commit()

    def fake_vl(**kwargs):
        images = kwargs.get("images") or []
        return [
            {
                "source_id": sid,
                "dimensions": {
                    "topic_relevance": {"score": 8, "signals": []},
                    "info_value": {"score": 8, "signals": []},
                    "visual_quality": {"score": 8, "signals": []},
                    "flash_fit": {"score": 8, "signals": []},
                    "compliance": {"score": 8, "signals": []},
                },
                "penalties": [],
                "caption": "test",
                "verdict": "ok",
                "reject": False,
            }
            for sid, _ in images
        ]

    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        fake_vl,
    )
    app = FastAPI()
    app.include_router(_load_ingestion_router())
    return TestClient(app)


def test_score_images_endpoint_returns_ranked_results(client):
    resp = client.post(
        "/api/ingestion/articles/art_api/score-images",
        json={"force": True, "include_story_images": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["scored_count"] >= 1
    assert body["images"][0]["relevance_rank"] == 1
    assert "relevance_grade" in body["images"][0]


def test_score_images_404_for_missing_article(client):
    resp = client.post(
        "/api/ingestion/articles/nope/score-images",
        json={"force": True},
    )
    assert resp.status_code == 404


def test_score_images_400_without_vision_model(client, monkeypatch):
    from services.ingestion import image_score_vl

    monkeypatch.setattr(image_score_vl, "get_vision_client", lambda: (None, None))
    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        image_score_vl.score_images_batch,
    )
    resp = client.post(
        "/api/ingestion/articles/art_api/score-images",
        json={"force": True},
    )
    assert resp.status_code == 400
    assert "视觉模型" in resp.json()["detail"]
