"""Pattern ranking: candidates, validation, fallback, draft integration."""
from __future__ import annotations

import json

import pytest

from services.copy_agent.card_schema import ranking_preview_from_card
from services.copy_agent.drafts import NoPlaybook, generate_one_draft
from services.copy_agent.pattern_library import cluster_key_for
from services.copy_agent.pattern_ranking import (
    build_ranking_candidates,
    choose_playbook_from_ranking,
    rank_playbook_for_material,
    resolve_representative_version_id,
    validate_ranking_response,
)
from services.copy_agent.settings_store import get_settings
from src.db.engine import get_session_factory, init_db
from src.db.models.playbook import CopyAgentJob, CopyDraft, PatternCard, PlaybookVersion


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "rank.db"
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


def test_settings_defaults_for_ranking(db_session):
    settings = get_settings(db_session)
    assert settings.material_adaptive_playbook is True
    assert settings.auto_material_adaptive_playbook is False
    assert settings.ranking_max_candidates == 40


def test_cluster_key_normalizes_name():
    assert cluster_key_for("opinion", "对照 开场") == "opinion|对照开场"


def test_ranking_preview_omits_evidence():
    preview = ranking_preview_from_card(
        {
            "pattern_name": "对照开场",
            "genre_label": "观点评论",
            "purpose": "先立场",
            "moves": [{"id": "1", "function": "hook"}],
            "hook": {"archetype_label": "对照"},
            "motives": {"primary_label": "好奇"},
            "verdict_function_label": "观点评论",
            "evidence_excerpt": "不应出现",
        }
    )
    assert "evidence_excerpt" not in preview
    assert preview["pattern_name"] == "对照开场"


def test_validate_rejects_unknown_cluster():
    with pytest.raises(ValueError):
        validate_ranking_response(
            {"chosen_cluster_key": "b|two", "ranked": [], "confidence": "high"},
            {"a|one"},
        )


def test_low_confidence_falls_back_to_current():
    candidates = [{"cluster_key": "opinion|a", "representative_version_id": "rec"}]
    parsed = {
        "chosen_cluster_key": "opinion|a",
        "confidence": "low",
        "ranked": [{"cluster_key": "opinion|a", "score": 0.6}],
    }
    vid, fallback, recommended = choose_playbook_from_ranking(
        parsed, candidates, current_version_id="cur"
    )
    assert fallback is True
    assert vid == "cur"
    assert recommended == "rec"


def test_low_confidence_without_current_returns_none():
    candidates = [{"cluster_key": "opinion|a", "representative_version_id": "rec"}]
    parsed = {
        "chosen_cluster_key": "opinion|a",
        "confidence": "low",
        "ranked": [{"cluster_key": "opinion|a", "score": 0.6}],
    }
    vid, fallback, _ = choose_playbook_from_ranking(
        parsed, candidates, current_version_id=None
    )
    assert vid is None
    assert fallback is True


def test_resolve_picks_published_with_body(db_session):
    db_session.add_all(
        [
            PlaybookVersion(id="a", body="one", status="published", trap_passed=True),
            PlaybookVersion(id="b", body="", status="published", trap_passed=True),
        ]
    )
    db_session.commit()
    chosen = resolve_representative_version_id(db_session, ["a", "b"])
    assert chosen == "a"


def _seed_ranked_cluster(db_session, *, version_id: str, current_id: str):
    db_session.add(
        PlaybookVersion(
            id=version_id,
            body="推荐打法正文",
            status="published",
            trap_passed=True,
        )
    )
    db_session.add(
        PlaybookVersion(
            id=current_id,
            body="当前打法正文",
            status="published",
            trap_passed=True,
        )
    )
    db_session.add(
        CopyAgentJob(
            id="job1",
            kind="curate",
            status="candidate",
            result_json=json.dumps({"playbook_version_id": version_id}, ensure_ascii=False),
        )
    )
    card = {
        "pattern": {"name": "测试模式", "genre": "short_news_commentary", "purpose": "测"},
        "moves": [{"id": "hook", "function": "钩"}],
        "hook": {"archetype": "curiosity_gap"},
        "motives": {"primary": "emotional_arousal"},
        "verdict": {"kind": "opinion", "function": "controversy_commentary"},
        "evidence_excerpt": "锚",
    }
    db_session.add(
        PatternCard(
            source_job_id="job1",
            card_json=json.dumps(card, ensure_ascii=False),
            verdict_kind="opinion",
            verdict_function="controversy_commentary",
        )
    )
    settings = get_settings(db_session)
    settings.current_playbook_version_id = current_id
    settings.material_adaptive_playbook = True
    db_session.commit()
    return cluster_key_for("short_news_commentary", "测试模式")


def test_rank_picks_cluster_from_mock_complete(db_session):
    key = _seed_ranked_cluster(db_session, version_id="v_rank", current_id="v_cur")

    def complete_rank(_messages):
        return json.dumps(
            {
                "chosen_cluster_key": key,
                "confidence": "high",
                "ranked": [{"cluster_key": key, "score": 0.9, "reason": "题材贴合"}],
            },
            ensure_ascii=False,
        )

    sel = rank_playbook_for_material(
        db_session,
        title="标题",
        content="摘要",
        complete_rank=complete_rank,
        adaptive=True,
        current_version_id="v_cur",
        max_candidates=40,
    )
    assert sel["fallback"] is False
    assert sel["playbook_version_id"] == "v_rank"


def test_draft_uses_ranked_version(db_session):
    key = _seed_ranked_cluster(db_session, version_id="v_rank", current_id="v_cur")

    def complete_rank(_messages):
        return json.dumps(
            {
                "chosen_cluster_key": key,
                "confidence": "high",
                "ranked": [{"cluster_key": key, "score": 0.9, "reason": "ok"}],
            },
            ensure_ascii=False,
        )

    draft = generate_one_draft(
        db_session,
        title="t",
        content="大约快 8 倍",
        complete=lambda _m: "大约快 8 倍",
        complete_rank=complete_rank,
    )
    assert draft.playbook_version_id == "v_rank"
    sel = json.loads(draft.selection_json)
    assert sel.get("fallback") is False


def test_battle_report_includes_fallback_count(db_session):
    from services.copy_agent.battle_report import build_battle_report

    db_session.add(
        CopyDraft(
            id="d1",
            playbook_version_id="v",
            selection_json=json.dumps({"fallback": True}, ensure_ascii=False),
        )
    )
    db_session.commit()
    report = build_battle_report(db_session)
    assert report["selection_fallback_count"] >= 1


def test_no_candidates_and_no_current_raises(db_session):
    settings = get_settings(db_session)
    settings.material_adaptive_playbook = True
    settings.current_playbook_version_id = None
    db_session.commit()

    with pytest.raises(NoPlaybook):
        rank_playbook_for_material(
            db_session,
            title="t",
            content="c",
            complete_rank=lambda _m: "{}",
            adaptive=True,
            current_version_id=None,
            max_candidates=40,
        )


def test_build_candidates_skips_empty_body(db_session):
    db_session.add(PlaybookVersion(id="empty", body="", status="published", trap_passed=True))
    db_session.add(
        CopyAgentJob(
            id="j",
            kind="curate",
            status="candidate",
            result_json=json.dumps({"playbook_version_id": "empty"}),
        )
    )
    card = {
        "pattern": {"name": "空体", "genre": "short_news_commentary", "purpose": "x"},
        "moves": [],
        "hook": {},
        "motives": {"primary": "emotional_arousal"},
        "verdict": {"kind": "opinion", "function": "controversy_commentary"},
    }
    db_session.add(
        PatternCard(
            source_job_id="j",
            card_json=json.dumps(card, ensure_ascii=False),
            verdict_kind="opinion",
            verdict_function="controversy_commentary",
        )
    )
    db_session.commit()
    assert build_ranking_candidates(db_session) == []
