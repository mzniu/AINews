"""Homepage playbook draft: one shot, fact gate, no model without a playbook."""
from __future__ import annotations

import json

import pytest

from services.copy_agent.drafts import NoPlaybook, draft_selectable, generate_one_draft, select_draft
from services.copy_agent.settings_store import get_settings
from src.db.engine import get_session_factory, init_db
from src.db.models.playbook import PlaybookVersion


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "drafts.db"
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


def test_drafts_do_not_call_model_without_current_playbook(db_session):
    called = {"n": 0}

    def complete(messages):
        called["n"] += 1
        return "口播"

    with pytest.raises(NoPlaybook):
        generate_one_draft(db_session, title="t", content="c", complete=complete)
    assert called["n"] == 0


def test_draft_with_ten_x_is_not_selectable(db_session):
    db_session.add(
        PlaybookVersion(id="v", body="对照放前三秒", status="published", trap_passed=True)
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "v"
    db_session.commit()

    draft = generate_one_draft(
        db_session,
        title="开源对标",
        content="大约快 8 倍",
        complete=lambda messages: "快 10 倍",
    )
    assert json.loads(draft.fact_gate_json)["passed"] is False
    assert draft_selectable(draft) is False
    assert draft.playbook_version_id == "v"


def test_json_field_names_are_not_fact_gate_numbers(db_session):
    db_session.add(
        PlaybookVersion(id="v", body="对照放前三秒", status="published", trap_passed=True)
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "v"
    db_session.commit()
    payload = json.dumps(
        {
            "main_line1": "对照放前三秒",
            "main_line2": "大约快 8 倍",
            "voiceover_script": "大约快 8 倍",
        },
        ensure_ascii=False,
    )
    draft = generate_one_draft(
        db_session,
        title="开源对标",
        content="大约快 8 倍",
        complete=lambda messages: payload,
    )
    assert json.loads(draft.fact_gate_json)["passed"] is True
    assert draft_selectable(draft) is True


def test_select_edited_keeps_version(db_session):
    db_session.add(
        PlaybookVersion(id="v", body="对照放前三秒", status="published", trap_passed=True)
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "v"
    db_session.commit()
    draft = generate_one_draft(
        db_session,
        title="开源对标",
        content="对照放前三秒",
        complete=lambda messages: "对照放前三秒",
    )
    selected = select_draft(db_session, draft.id, edited=True)
    assert selected.playbook_version_id == "v"
    assert selected.edited_after_select is True
    assert selected.selected is True
