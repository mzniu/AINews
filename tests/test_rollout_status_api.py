"""API tests for publish policy rollout status."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db.engine import init_db


def _load_publishing_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes_rollout", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_rollout.db"
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


def test_rollout_status_endpoint_returns_policy_payload(client):
    response = client.get("/api/publishing/rollout/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "policy_version" in payload
    assert "platforms" in payload
    assert "queue" in payload
