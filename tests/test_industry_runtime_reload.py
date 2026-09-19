"""Industry switch triggers ingestion schedule reload without process restart."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.industry.runtime_reload import reload_industry_runtime
from services.ingestion.worker import SCHEDULE_RELOAD_FLAG
from web_server import app

import src.db.engine as engine_mod
from src.db.engine import get_session_factory, init_db


def _reset_db_engine() -> None:
    engine_mod._engine = None
    engine_mod._SessionLocal = None


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "ainews.db"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    _reset_db_engine()
    init_db()
    session = get_session_factory()()
    yield session
    session.close()
    _reset_db_engine()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    _reset_db_engine()
    init_db()
    monkeypatch.delenv("AINES_DEV_MODE", raising=False)
    monkeypatch.delenv("AINEWS_ACTIVE_INDUSTRY_ID", raising=False)
    yield TestClient(app)
    _reset_db_engine()


def test_reload_industry_runtime_refreshes_embedded_worker(db_session):
    worker = MagicMock()
    worker.scheduler.running = True
    result = reload_industry_runtime(db_session, worker)
    assert result["embedded_schedules_refreshed"] is True
    assert result["runtime_reloaded"] is True
    worker.refresh_schedules.assert_called_once()


def test_reload_industry_runtime_signals_separate_worker(
    db_session, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    monkeypatch.setenv("INGESTION_WORKER_MODE", "separate")
    if SCHEDULE_RELOAD_FLAG.is_file():
        SCHEDULE_RELOAD_FLAG.unlink()

    result = reload_industry_runtime(db_session, None)
    assert result["separate_worker_signaled"] is True
    assert result["runtime_reloaded"] is True
    assert SCHEDULE_RELOAD_FLAG.is_file()


def test_switch_industry_auto_reloads_runtime(client):
    worker = MagicMock()
    worker.scheduler.running = True
    client.app.state.ingestion_worker = worker

    response = client.post(
        "/api/me/industry/switch",
        json={"active_industry_id": "finance/macro"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("restart_required") is False
    assert body.get("runtime_reloaded") is True
    assert body.get("embedded_schedules_refreshed") is True
    worker.refresh_schedules.assert_called_once()
