"""Ingestion API smoke tests (load router module directly to avoid api.routes __init__)."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.ingestion.registry import sync_sources_to_db
from src.db.engine import init_db, get_session_factory


def _load_ingestion_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "ingestion_routes.py"
    spec = importlib.util.spec_from_file_location("ingestion_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_api.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    with get_session_factory()() as session:
        sync_sources_to_db(session)
        session.commit()
    app = FastAPI()
    app.include_router(_load_ingestion_router())
    return TestClient(app)


def test_list_sources(client):
    resp = client.get("/api/ingestion/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert any(s["id"] == "aitnt_travel" for s in data)


def test_enqueue_run(client):
    resp = client.post("/api/ingestion/sources/aitnt_travel/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["job_id"]
