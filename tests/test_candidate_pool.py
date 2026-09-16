"""API tests for candidate pool management."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db.engine import init_db


def _load_publishing_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes_candidate_pool", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_candidate_pool.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    init_db()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def test_list_candidates_empty(client):
    response = client.get("/api/publishing/candidates")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total"] == 0
    assert payload["items"] == []


def test_skip_unknown_candidate_returns_404(client):
    response = client.post("/api/publishing/candidates/no-such-id/skip")
    assert response.status_code == 404


def test_enqueue_unknown_candidate_returns_404(client):
    response = client.post("/api/publishing/candidates/no-such-id/enqueue")
    assert response.status_code == 404


def test_skip_and_list_candidate(client):
    from src.db.engine import session_scope
    from src.db.models.ingestion import IngestedArticle, IngestionSource
    from src.db.models.publishing import AutoPublishCandidate

    with session_scope() as session:
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
        session.flush()
        article = IngestedArticle(
            source_id="src1",
            canonical_url="https://example.com/candidate-pool",
            title="candidate-pool-test",
        )
        session.add(article)
        session.flush()
        candidate = AutoPublishCandidate(
            article_id=article.id,
            platform="douyin",
            policy_version="1",
            action="publish",
            recommended_action="publish",
            priority=88.0,
            reasons_json='["test"]',
            status="pending",
        )
        session.add(candidate)
        session.flush()
        candidate_id = candidate.id

    listed = client.get("/api/publishing/candidates?status=pending&platform=douyin")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "candidate-pool-test"

    skipped = client.post(f"/api/publishing/candidates/{candidate_id}/skip")
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped"
