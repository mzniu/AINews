"""Playbook version list for the pattern lab."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.copy_agent.settings_store import get_settings
from src.db.engine import get_session_factory, init_db
from src.db.models.playbook import CopyAgentJob, PatternCard, PlaybookVersion


@pytest.fixture
def client(db_session):
    from api.routes.copy_agent_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "versions.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    init_db()
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def test_list_versions_marks_current(client, db_session):
    db_session.add(
        PlaybookVersion(id="old", body="旧打法", status="published", trap_passed=True)
    )
    db_session.add(
        PlaybookVersion(id="new", body="新打法正文", status="published", trap_passed=True)
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "new"
    db_session.commit()

    body = client.get("/api/copy-agent/versions").json()
    assert body["current_playbook_version_id"] == "new"
    assert len(body["versions"]) == 2
    current = [v for v in body["versions"] if v["is_current"]]
    assert len(current) == 1
    assert current[0]["id"] == "new"
    assert "新打法" in current[0]["body_preview"]


def test_version_detail_includes_card(client, db_session):
    db_session.add(
        PlaybookVersion(
            id="v1",
            body="对照放前三秒",
            diff_json="body: |\n  对照放前三秒\n",
            status="candidate",
            trap_passed=True,
        )
    )
    db_session.add(
        CopyAgentJob(
            id="job1",
            kind="curate",
            status="candidate",
            result_json=json.dumps({"playbook_version_id": "v1"}, ensure_ascii=False),
        )
    )
    db_session.add(
        PatternCard(
            source_job_id="job1",
            verdict_kind="opinion",
            verdict_function="controversy_commentary",
            card_json='{"pattern":{"name":"测试模式","genre":"short_news_commentary","purpose":"测"},"moves":[{"id":"hook","function":"钩"},{"id":"x","function":"收"}],"hook":{"archetype":"curiosity_gap"},"motives":{"primary":"emotional_arousal"},"verdict":{"kind":"opinion","function":"controversy_commentary"},"evidence_excerpt":"锚点"}',
            forbidden_transfers_json=json.dumps(["10倍"], ensure_ascii=False),
        )
    )
    db_session.commit()
    detail = client.get("/api/copy-agent/versions/v1").json()
    assert detail["body"] == "对照放前三秒"
    assert "对照放前三秒" in detail["diff_yaml"]
    assert detail["card_preview"]["verdict_kind"] == "opinion"
    assert detail["card_preview"]["verdict_function"] == "controversy_commentary"
    assert detail["card_preview"]["pattern_name"] == "测试模式"
    assert detail["card_preview"]["forbidden_transfers"] == ["10倍"]
