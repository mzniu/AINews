"""dsh curate sandbox: path audit, env allowlist, and fake runner."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from services.copy_agent.audit import audit_tool_paths, harness_env
from services.copy_agent.curate import run_curate, start_dsh
from tests.playbook_card_fixtures import minimal_card_yaml, write_curate_draft_files
from src.db.engine import get_session_factory, init_db
from src.db.models.playbook import PatternCard, PlaybookVersion


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "playbook.db"
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


def _tool_line(**data):
    return json.dumps({"type": "tool/call", "data": data})


def test_audit_rejects_path_outside_workspace(tmp_path):
    workspace = tmp_path / "job"
    workspace.mkdir()
    line = _tool_line(arguments=json.dumps({"command": "type D:/git/AINews/.env"}))
    assert audit_tool_paths(line + "\n", [workspace]) == ["D:/git/AINews/.env"]


def test_audit_accepts_path_inside_workspace(tmp_path):
    workspace = tmp_path / "job"
    drafts = workspace / "drafts"
    drafts.mkdir(parents=True)
    inside = drafts / "card.yaml"
    line = _tool_line(arguments=json.dumps({"command": f"Get-Content {inside}"}))
    assert audit_tool_paths(line + "\n", [workspace]) == []


def test_audit_ignores_slashes_that_are_not_paths(tmp_path):
    workspace = tmp_path / "job"
    workspace.mkdir()
    line = json.dumps({"text": "大约快 8/10", "note": "\\n", "slash": "/"})
    assert audit_tool_paths(line + "\n", [workspace]) == []


def test_audit_ignores_tool_text_glued_onto_an_inside_path(tmp_path):
    workspace = tmp_path / "job"
    workspace.mkdir()
    line = json.dumps({"text": str(workspace) + "Mode   : d-----"})
    assert audit_tool_paths(line + "\n", [workspace]) == []


def test_audit_rejects_relative_escape(tmp_path):
    workspace = tmp_path / "job"
    workspace.mkdir()
    line = _tool_line(path="..\\..\\Windows\\System32")
    assert audit_tool_paths(line + "\n", [workspace]) == ["..\\..\\Windows\\System32"]


def test_audit_ignores_assistant_reasoning_paths(tmp_path):
    workspace = tmp_path / "job"
    workspace.mkdir()
    prose = r"D:\git\AINews\data\copy_agent\workspaces\..."
    line = json.dumps(
        {
            "type": "assistant/message",
            "data": {
                "message": {
                    "content": [{"type": "reasoning", "text": f"write only under {prose}"}],
                }
            },
        }
    )
    assert audit_tool_paths(line + "\n", [workspace]) == []


def test_audit_ignores_dotdot_prose(tmp_path):
    workspace = tmp_path / "job"
    workspace.mkdir()
    line = json.dumps({"text": "C:\\\\...)"})
    assert audit_tool_paths(line + "\n", [workspace]) == []


def test_harness_env_drops_unlisted_secrets():
    env = harness_env({"PATH": "C:\\Windows", "DEEPSEEK_API_KEY": "sk", "AWS_SECRET": "nope"})
    assert "AWS_SECRET" not in env
    assert env["DEEPSEEK_API_KEY"] == "sk"
    assert env["PATH"] == "C:\\Windows"


def test_curate_needs_text_does_not_call_runner(db_session):
    called = {"n": 0}

    def runner(workspace, session_root, session_id, env):
        called["n"] += 1

    job = run_curate(db_session, text="  ", runner=runner)
    assert job.status == "needs_text"
    assert called["n"] == 0


def test_curate_discards_yaml_when_tool_path_escapes(db_session):
    def runner(workspace, session_root, session_id, env):
        write_curate_draft_files(workspace)
        session_root.mkdir(parents=True, exist_ok=True)
        (session_root / "session.jsonl").write_text(
            _tool_line(arguments=json.dumps({"command": "type D:/git/AINews/.env"})) + "\n",
            encoding="utf-8",
        )

    job = run_curate(db_session, text="三年对三天", runner=runner)
    assert job.status == "rejected_escape"
    assert db_session.query(PatternCard).count() == 0
    assert db_session.query(PlaybookVersion).count() == 0


def test_curate_rejects_incomplete_v2_card(db_session):
    def runner(workspace, session_root, session_id, env):
        (workspace / "drafts").mkdir(exist_ok=True)
        (workspace / "drafts" / "analysis.md").write_text("move hook\nframe 数字\n" + "x" * 60, encoding="utf-8")
        (workspace / "drafts" / "card.yaml").write_text(
            "verdict:\n  kind: opinion\n  function: controversy_commentary\n", encoding="utf-8"
        )
        from tests.playbook_card_fixtures import minimal_diff_yaml

        (workspace / "drafts" / "playbook.diff.yaml").write_text(minimal_diff_yaml(), encoding="utf-8")
        session_root.mkdir(parents=True, exist_ok=True)
        (session_root / "session.jsonl").write_text("{}\n", encoding="utf-8")

    job = run_curate(db_session, text="三年对三天", runner=runner)
    assert job.status == "rejected_schema"
    assert db_session.query(PatternCard).count() == 0


def test_curate_rejects_non_opinion_verdict(db_session):
    def runner(workspace, session_root, session_id, env):
        write_curate_draft_files(workspace)
        (workspace / "drafts" / "card.yaml").write_text(
            "verdict:\n  kind: fact\n  function: controversy_commentary\n", encoding="utf-8"
        )
        session_root.mkdir(parents=True, exist_ok=True)
        (session_root / "session.jsonl").write_text("{}\n", encoding="utf-8")

    job = run_curate(db_session, text="三年对三天", runner=runner)
    assert job.status == "rejected_schema"
    assert db_session.query(PatternCard).count() == 0


def test_curate_stores_card_and_marks_trap_failure(db_session):
    def runner(workspace, session_root, session_id, env):
        write_curate_draft_files(workspace, extra_body_line="多项评测全面超越")
        session_root.mkdir(parents=True, exist_ok=True)
        inside = workspace / "drafts" / "card.yaml"
        (session_root / "session.jsonl").write_text(
            json.dumps({"path": str(inside)}) + "\n", encoding="utf-8"
        )

    job = run_curate(db_session, text="三年对三天", runner=runner)
    assert job.status == "candidate"
    payload = json.loads(job.result_json or "{}")
    assert payload.get("card_preview", {}).get("pattern_name")
    assert db_session.query(PatternCard).count() == 1
    version = db_session.query(PlaybookVersion).one()
    assert version.status == "candidate"
    assert version.trap_passed is False
    assert "全面超越" in version.body


def test_start_dsh_uses_sdk_with_allowlisted_env(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    captured = {}

    class FakeHarness:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
            self.kwargs = kwargs

        def __enter__(self):
            home = Path(self.kwargs["dsh_home"])
            sessions = home / "sessions"
            sessions.mkdir()
            (sessions / "job1.jsonl").write_text('{"path":"drafts/card.yaml"}\n', encoding="utf-8")
            subprocess.Popen(["dsh"])
            return self

        def __exit__(self, *args):
            return False

        def run(self, prompt, session_id):
            captured.setdefault("runs", []).append({"prompt": prompt, "session_id": session_id})
            captured["prompt"] = prompt
            captured["session_id"] = session_id
            return SimpleNamespace(final_response="ok")

    def fake_popen(*args, **kwargs):
        captured["popen_env"] = kwargs.get("env")
        return SimpleNamespace()

    monkeypatch.setattr("services.copy_agent.curate.subprocess.Popen", fake_popen)
    monkeypatch.setitem(sys.modules, "deepseek_harness", SimpleNamespace(DeepSeekHarness=FakeHarness))
    monkeypatch.setenv("AWS_SECRET", "nope")
    workspace = tmp_path / "ws"
    session_root = tmp_path / "sess"
    workspace.mkdir()
    (workspace / "material.txt").write_text("三年对三天", encoding="utf-8")
    session_root.mkdir()
    start_dsh(
        workspace,
        session_root,
        "job1",
        harness_env({"PATH": "C:\\Windows", "DEEPSEEK_API_KEY": "sk-test", "DEEPSEEK_MODEL": "deepseek-chat"}),
    )
    assert captured["kwargs"]["cwd"] == str(workspace.resolve())
    assert captured["kwargs"]["dsh_home"] == str(session_root.resolve())
    assert captured["kwargs"]["profile"] == "sdk-minimal"
    assert captured["kwargs"]["model"] == "deepseek-chat"
    assert len(captured["runs"]) == 2
    assert "第一步" in captured["runs"][0]["prompt"]
    assert "第二步" in captured["runs"][1]["prompt"]
    assert captured["runs"][1]["session_id"] == "job1-b"
    assert captured["kwargs"]["request_timeout_seconds"] == 180
    assert "AWS_SECRET" not in captured["kwargs"]["env"]
    assert captured["kwargs"]["env"]["DEEPSEEK_API_KEY"] == "sk-test"
    assert "AWS_SECRET" not in captured["popen_env"]
    assert captured["popen_env"]["DEEPSEEK_API_KEY"] == "sk-test"
    assert "drafts/card.yaml" in (session_root / "session.jsonl").read_text(encoding="utf-8")
    assert os.environ["AWS_SECRET"] == "nope"
