"""API tests for model token usage endpoints."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db.engine import init_db, get_session_factory
from services.model_config.token_usage import record_token_usage


def _load_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "model_config_routes.py"
    spec = importlib.util.spec_from_file_location("model_config_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "usage_api.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    app = FastAPI()
    app.include_router(_load_router())
    return TestClient(app)


def test_usage_summary_empty(client):
    resp = client.get("/api/models/usage", params={"range": "all"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["totals"]["calls"] == 0


def test_usage_summary_and_clear(client):
    factory = get_session_factory()
    with factory() as session:
        record_token_usage(
            kind="language",
            profile_id="p1",
            provider="deepseek",
            model="deepseek-chat",
            task="content_gen",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            session=session,
        )
        session.commit()
    resp = client.get("/api/models/usage", params={"range": "all"})
    assert resp.json()["totals"]["total_tokens"] == 15
    cleared = client.post("/api/models/usage/clear")
    assert cleared.status_code == 200
    assert client.get("/api/models/usage", params={"range": "all"}).json()["totals"]["calls"] == 0


def test_usage_rejects_bad_range(client):
    resp = client.get("/api/models/usage", params={"range": "yesterday"})
    assert resp.status_code == 400
