"""POST /api/ingestion/articles/{id}/playbook-draft writes video_draft_json."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.copy_agent.settings_store import get_settings
from services.ingestion.registry import sync_sources_to_db
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle
from src.db.models.playbook import PlaybookVersion


def _load_ingestion_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "ingestion_routes.py"
    spec = importlib.util.spec_from_file_location("ingestion_routes_playbook", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "ing_playbook.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    init_db()
    with get_session_factory()() as session:
        sync_sources_to_db(session)
        session.commit()
    app = FastAPI()
    app.include_router(_load_ingestion_router())
    return TestClient(app)


def _seed_playbook_and_article():
    session = get_session_factory()()
    session.add(
        PlaybookVersion(id="v1", body="对照放前三秒", status="published", trap_passed=True)
    )
    settings = get_settings(session)
    settings.current_playbook_version_id = "v1"
    session.add(
        IngestedArticle(
            id="art_pb",
            source_id="aitnt_travel",
            canonical_url="https://example.com/a",
            title="开源对标",
            content_text="大约快 8 倍",
        )
    )
    session.commit()
    session.close()


def test_playbook_draft_writes_video_draft(client, monkeypatch):
    _seed_playbook_and_article()
    payload = json.dumps(
        {
            "main_line1": "对照放前三秒",
            "voiceover_script": "大约快 8 倍",
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "api.routes.copy_agent_routes.production_complete",
        lambda messages: payload,
    )
    resp = client.post("/api/ingestion/articles/art_pb/playbook-draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_draft"]["main_line1"] == "对照放前三秒"
    assert body["video_draft"]["playbook_attribution"] == "playbook"
    assert body["video_draft"]["playbook_version_id"] == "v1"
    assert body["video_draft"]["copy_draft_id"]


def test_playbook_draft_409_without_playbook(client, monkeypatch):
    session = get_session_factory()()
    session.add(
        IngestedArticle(
            id="art_nopb",
            source_id="aitnt_travel",
            canonical_url="https://example.com/b",
            title="t",
            content_text="正文",
        )
    )
    session.commit()
    session.close()
    monkeypatch.setattr(
        "api.routes.copy_agent_routes.production_complete",
        lambda messages: "x",
    )
    resp = client.post("/api/ingestion/articles/art_nopb/playbook-draft")
    assert resp.status_code == 409
