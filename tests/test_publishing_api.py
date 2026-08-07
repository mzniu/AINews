import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db.engine import init_db


def _load_publishing_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_publishing.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def test_list_platforms(client):
    resp = client.get("/api/publishing/platforms")
    assert resp.status_code == 200
    data = resp.json()
    wechat = next(p for p in data["platforms"] if p["id"] == "wechat_channels")
    assert wechat["capabilities"]["video_publish"] is True


def test_qr_start_rejects_unknown_platform(client):
    resp = client.post(
        "/api/publishing/accounts/qr-start",
        json={"platform": "unknown_platform"},
    )
    assert resp.status_code in {400, 404}


def test_qr_start_accepts_enabled_douyin(client):
    resp = client.post(
        "/api/publishing/accounts/qr-start",
        json={"platform": "douyin", "purpose": "create"},
    )
    assert resp.status_code == 200
    assert resp.json().get("session_id")


def test_create_job_rejects_missing_video(client, tmp_path, monkeypatch):
    from src.utils.config import Config

    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    (tmp_path / "data" / "videos").mkdir(parents=True)
    init_db()
    resp = client.post(
        "/api/publishing/jobs",
        json={
            "account_id": "missing",
            "video_path": "/data/videos/nope.mp4",
            "title": "标题",
        },
    )
    assert resp.status_code in {400, 404}
