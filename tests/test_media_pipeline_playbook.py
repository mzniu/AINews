"""Auto pipeline uses the current playbook only when the switch is on."""
from __future__ import annotations

import json

import pytest

from services.copy_agent.settings_store import get_settings
from services.ingestion.media_pipeline import run_media_pipeline
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.db.models.playbook import PlaybookVersion


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "pipeline.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="aitnt_news",
            enabled=True,
            schedule_cron="0 * * * *",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _article(session) -> IngestedArticle:
    row = IngestedArticle(
        id="art1",
        source_id="src1",
        canonical_url="https://example.com/a",
        title="开源对标",
        content_text="社区做出对标实现",
        summary="社区做出对标实现",
    )
    session.add(row)
    session.commit()
    return row


def _content_only_config() -> dict:
    return {
        "post_score_automation": {
            "media_pipeline": {
                "score_images": False,
                "generate_content": True,
                "prepare_video": False,
                "render_video": False,
                "render_cover": False,
                "random_bgm": False,
            }
        }
    }


def test_gate_failure_falls_back_without_playbook(db_session, monkeypatch):
    db_session.add(
        PlaybookVersion(id="v", body="快 10 倍", status="published", trap_passed=False)
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "v"
    settings.auto_uses_current_playbook = True
    db_session.commit()
    article = _article(db_session)
    calls = []

    def fake_generate(**kwargs):
        body = kwargs.get("playbook_body")
        calls.append(body)
        summary = "快 10 倍" if body else "宪法口播"
        return {
            "success": True,
            "title": "标题",
            "main_line1": "标题",
            "summary": summary,
            "voiceover_script": summary,
            "tags": [],
            "model": "fake",
        }

    monkeypatch.setattr("services.ingestion.media_pipeline.generate_video_content", fake_generate)
    run_media_pipeline(db_session, article.id, config=_content_only_config())
    db_session.refresh(article)
    saved = json.loads(article.video_draft_json)
    assert None in calls
    assert saved["summary"] == "宪法口播"
    assert saved["playbook_attribution"] == "fact_gate_fallback"
    assert saved["playbook_version_id"] is None
    assert saved["copy_draft_id"] is None


def test_switch_off_omits_playbook_fields(db_session, monkeypatch):
    article = _article(db_session)

    def fake_generate(**kwargs):
        assert kwargs.get("playbook_body") in (None, "")
        return {
            "success": True,
            "title": "标题",
            "main_line1": "标题",
            "summary": "宪法口播",
            "voiceover_script": "宪法口播",
            "tags": [],
            "model": "fake",
        }

    monkeypatch.setattr("services.ingestion.media_pipeline.generate_video_content", fake_generate)
    run_media_pipeline(db_session, article.id, config=_content_only_config())
    db_session.refresh(article)
    saved = json.loads(article.video_draft_json)
    assert "playbook_attribution" not in saved
    assert "playbook_version_id" not in saved


def test_pipeline_skips_rank_when_only_auto_uses(db_session, monkeypatch):
    db_session.add(
        PlaybookVersion(id="v", body="对照放前三秒", status="published", trap_passed=True)
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "v"
    settings.auto_uses_current_playbook = True
    settings.auto_material_adaptive_playbook = False
    db_session.commit()
    article = _article(db_session)
    rank_calls = {"n": 0}

    def fake_rank(*args, **kwargs):
        rank_calls["n"] += 1
        raise AssertionError("rank should not run")

    monkeypatch.setattr(
        "services.copy_agent.pattern_ranking.rank_playbook_for_material",
        fake_rank,
    )

    def fake_generate(**kwargs):
        assert kwargs.get("playbook_body") == "对照放前三秒"
        return {
            "success": True,
            "title": "标题",
            "main_line1": "标题",
            "summary": "对照口播",
            "voiceover_script": "对照口播",
            "tags": [],
            "model": "fake",
        }

    monkeypatch.setattr("services.ingestion.media_pipeline.generate_video_content", fake_generate)
    run_media_pipeline(db_session, article.id, config=_content_only_config())
    assert rank_calls["n"] == 0


def test_model_error_marks_generation_fallback(db_session, monkeypatch):
    db_session.add(
        PlaybookVersion(id="v", body="对照放前三秒", status="published", trap_passed=True)
    )
    db_session.commit()
    settings = get_settings(db_session)
    settings.current_playbook_version_id = "v"
    settings.auto_uses_current_playbook = True
    db_session.commit()
    article = _article(db_session)
    article.video_draft_json = json.dumps({"main_line1": "旧稿", "title": "旧稿"})
    db_session.commit()

    def fake_generate(**kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr("services.ingestion.media_pipeline.generate_video_content", fake_generate)
    run_media_pipeline(db_session, article.id, config=_content_only_config())
    db_session.refresh(article)
    saved = json.loads(article.video_draft_json)
    assert saved["playbook_attribution"] == "generation_fallback"
    assert saved["playbook_version_id"] is None
    assert saved["main_line1"] == "旧稿"
