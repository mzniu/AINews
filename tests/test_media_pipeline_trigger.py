"""Tests for media pipeline eligibility (S grade OR score >= 80)."""
from __future__ import annotations

from services.ingestion.media_pipeline_trigger import (
    load_media_pipeline_config,
    should_run_media_pipeline,
)


def test_load_media_pipeline_config_defaults():
    cfg = load_media_pipeline_config({})
    assert cfg["enabled"] is True
    assert cfg["trigger"]["min_grade"] == "S"
    assert cfg["trigger"]["min_score"] == 80
    assert cfg["render_video"] is True
    assert cfg["max_selected_images"] == 4


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
