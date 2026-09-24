"""HTTP tests for the dsh learning loop."""
from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.copy_agent.settings_store import get_settings
from tests.playbook_card_fixtures import write_curate_draft_files
from src.db.engine import get_session_factory, init_db
from src.db.models.playbook import PlaybookVersion


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "playbook_api.db"
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


@pytest.fixture
def client(db_session):
    from api.routes.copy_agent_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_orphaned_running_curate_is_cleared_on_startup(db_session):
    from services.copy_agent.curate import fail_orphaned_curate_jobs
    from src.db.models.playbook import CopyAgentJob

    db_session.add(CopyAgentJob(kind="curate", status="running", result_json="{}"))
    db_session.commit()
    assert fail_orphaned_curate_jobs(db_session) == 1
    job = db_session.query(CopyAgentJob).filter_by(kind="curate").one()
    assert job.status == "failed"


def test_rank_preview_uses_mock_rank(client, db_session, monkeypatch):
    db_session.add(
        PlaybookVersion(
            id="v",
            body="正文",
            status="published",
            trap_passed=True,
        )
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "v"
    settings.material_adaptive_playbook = False
    db_session.commit()

    res = client.post(
        "/api/copy-agent/rank-preview",
        json={"title": "标题", "content": "摘要"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["selection"]["playbook_version_id"] == "v"
    assert body["material_adaptive_playbook"] is False
    assert body["ranked"] == []


def test_harness_not_ready_copy(client, monkeypatch):
    monkeypatch.setattr("api.routes.copy_agent_routes.dsh_installed", lambda: False)
    body = client.get("/api/copy-agent/harness").json()
    assert body["ready"] is False
    assert len(body["lines"]) == 3
    blob = "".join(body["lines"])
    for word in ("白名单", "JSONL", "ACL"):
        assert word not in blob
    assert "还不能拆爆款" in blob
    assert "未检测到 dsh" in blob


def test_publish_http_tells_user_to_disable_switch(client, db_session):
    settings = get_settings(db_session)
    settings.auto_uses_current_playbook = True
    settings.current_playbook_version_id = "old"
    db_session.add(
        PlaybookVersion(
            id="old",
            body="旧",
            status="published",
            trap_passed=True,
        )
    )
    db_session.add(
        PlaybookVersion(
            id="new",
            body="全面超越",
            status="candidate",
            trap_passed=False,
            parent_id="old",
        )
    )
    db_session.commit()
    res = client.post("/api/copy-agent/versions/new/publish")
    assert res.status_code == 409
    assert res.json()["hint"] == "disable_auto_switch"
    assert "先关掉" in res.json()["message"]
    db_session.expire_all()
    assert get_settings(db_session).current_playbook_version_id == "old"


def test_materials_uses_injected_runner(client, monkeypatch):
    def runner(workspace, session_root, session_id, env):
        write_curate_draft_files(workspace)
        session_root.mkdir(parents=True, exist_ok=True)
        (session_root / "session.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr("api.routes.copy_agent_routes.production_runner", runner)
    res = client.post("/api/copy-agent/materials", json={"text": "三年对三天"})
    assert res.status_code == 200
    body = res.json()
    job_id = body["job_id"]
    job = None
    for _ in range(40):
        job = client.get(f"/api/copy-agent/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job is not None
    assert job["status"] == "candidate"
    assert job["summary"] == "这次只写了草稿目录里的文件。"
    assert job["progress"]["phase"] == "done"
    assert "开场三秒内" in (job["playbook_body"] or "")
