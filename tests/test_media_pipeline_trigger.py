"""Tests for media pipeline eligibility (S grade OR score >= 80)."""
from __future__ import annotations

from services.ingestion.media_pipeline_trigger import (
    build_manual_media_retry_config,
    load_media_pipeline_config,
    resolve_cover_intro_duration_sec,
    should_run_media_pipeline,
)


def test_load_media_pipeline_config_defaults():
    cfg = load_media_pipeline_config({})
    assert cfg["enabled"] is True
    assert cfg["trigger"]["min_grade"] == "S"
    assert cfg["trigger"]["min_score"] == 80
    assert cfg["render_video"] is True
    assert cfg["max_selected_images"] == 4
    assert cfg["background_image"] == "static/imgs/bg.png"
    assert cfg["cover_width"] == 1080
    assert cfg["cover_height"] == 1920
    assert cfg["render_template_id"] in {"flash_news_portrait", "chronicle_archive_tech_blue"}
    assert cfg["layout_kind"] in {"classic_overlay", "chronicle_frame"}


def test_triggers_on_s_grade():
    assert should_run_media_pipeline(final_grade="S", final_total=70.0) is True


def test_triggers_on_score_80_even_if_grade_a():
    assert should_run_media_pipeline(final_grade="A", final_total=82.0) is True


def test_does_not_trigger_on_a_grade_below_80():
    assert should_run_media_pipeline(final_grade="A", final_total=75.0) is False


def test_does_not_trigger_when_neither_s_nor_score_threshold():
    assert should_run_media_pipeline(final_grade="A", final_total=75.0) is False
    assert should_run_media_pipeline(final_grade="B", final_total=60.0) is False


def test_score_80_triggers_without_s_grade():
    assert should_run_media_pipeline(final_grade="B", final_total=90.0) is True


def test_respects_disabled_config():
    cfg = {
        "post_score_automation": {
            "enabled": False,
            "media_pipeline": {"trigger": {"min_grade": "S", "min_score": 80}},
        }
    }
    assert should_run_media_pipeline(final_grade="S", final_total=90.0, config=cfg) is False


def test_min_grade_a_triggers_on_a_grade_even_below_score():
    cfg = {
        "post_score_automation": {
            "media_pipeline": {"trigger": {"min_grade": "A", "min_score": 80, "logic": "or"}},
        }
    }
    assert should_run_media_pipeline(final_grade="A", final_total=75.0, config=cfg) is True


def test_load_media_pipeline_honors_top_level_template_id():
    cfg = load_media_pipeline_config({"render_template_id": "chronicle_archive_tech_blue"})
    assert cfg["layout_kind"] == "chronicle_frame"
    assert cfg["render_template_id"] == "chronicle_archive_tech_blue"
    assert cfg["cover_height"] == 1920
    assert cfg["cover_width"] == 1080


def test_cover_intro_defaults_to_one_frame_at_canvas_fps():
    assert abs(resolve_cover_intro_duration_sec() - (1.0 / 24)) < 1e-9


def test_cover_intro_frames_win_over_legacy_duration():
    duration = resolve_cover_intro_duration_sec(
        video={"cover_intro_frames": 1, "cover_intro_duration_sec": 1.5},
        canvas={"fps": 24},
    )
    assert abs(duration - (1.0 / 24)) < 1e-9


def test_cover_intro_legacy_duration_when_no_frames():
    duration = resolve_cover_intro_duration_sec(
        video={"cover_intro_duration_sec": 1.5},
        canvas={"fps": 24},
    )
    assert duration == 1.5


def test_load_media_pipeline_cover_intro_is_one_frame():
    cfg = load_media_pipeline_config({})
    assert abs(cfg["cover_intro_duration_sec"] - (1.0 / 24)) < 1e-6


def test_load_chronicle_cover_intro_is_one_frame():
    cfg = load_media_pipeline_config({"render_template_id": "chronicle_archive_tech_blue"})
    assert abs(cfg["cover_intro_duration_sec"] - (1.0 / 24)) < 1e-6


def test_load_media_pipeline_honors_flat_retry_overrides():
    overrides = build_manual_media_retry_config(
        include_story_images=True, has_video_draft=True
    )
    cfg = load_media_pipeline_config(overrides)
    assert cfg["generate_content"] is False
    assert cfg["select_top_by_rank"] is True
    assert cfg["force_score_images"] is False
    assert cfg["include_story_images"] is True
    assert cfg["skip_if_done"] is False
