"""Tests for publisher account session status check."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config


def _load_publishing_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_account_status.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    init_db()
    factory = get_session_factory()
    session = factory()
    sessions_dir = tmp_path / "data" / "publish" / "sessions"
    sessions_dir.mkdir(parents=True)
    session_file = sessions_dir / "acc1.enc"
    session_file.write_bytes(b"encrypted-session")
    session.add(
        PublisherAccount(
            id="acc1",
            platform="wechat_channels",
            nickname="测试视频号",
            platform_uid="wx_test",
            session_path="data/publish/sessions/acc1.enc",
            status="active",
        )
    )
    session.commit()
    session.close()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def test_check_account_status_updates_to_expired(client):
    with patch(
        "services.publishing.account_status.get_adapter"
    ) as mock_get_adapter:
        adapter = mock_get_adapter.return_value
        adapter.validate_session.return_value = "expired"
        resp = client.post("/api/publishing/accounts/acc1/check-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "expired"
    assert "过期" in data["message"]


def test_check_account_status_keeps_active(client):
    with patch(
        "services.publishing.account_status.get_adapter"
    ) as mock_get_adapter:
        adapter = mock_get_adapter.return_value
        adapter.validate_session.return_value = "active"
        resp = client.post("/api/publishing/accounts/acc1/check-status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_check_account_status_not_found(client):
    resp = client.post("/api/publishing/accounts/missing/check-status")
    assert resp.status_code == 404
