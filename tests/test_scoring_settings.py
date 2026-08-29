"""Tests for article scoring local overrides."""
from __future__ import annotations

import yaml

from services.ingestion.scoring_settings import (
    get_auto_publish_settings,
    get_media_pipeline_settings,
    load_merged_scoring_config,
    save_auto_publish_settings,
    save_media_pipeline_settings,
    set_auto_publish_enabled,
)


def test_set_auto_publish_enabled_persists_local(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "article_scoring.yaml"
    local_path = tmp_path / "config" / "article_scoring.local.yaml"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(
        yaml.dump(
            {
                "post_score_automation": {
                    "auto_publish": {"enabled": True, "skip_if_exists": True},
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", local_path)

    assert get_auto_publish_settings()["enabled"] is True
    set_auto_publish_enabled(False)
    assert local_path.exists()
    assert get_auto_publish_settings()["enabled"] is False

    merged = load_merged_scoring_config()
    assert merged["post_score_automation"]["auto_publish"]["enabled"] is False
    assert merged["post_score_automation"]["auto_publish"]["skip_if_exists"] is True


def test_save_auto_publish_min_grade_persists_local(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "article_scoring.yaml"
    local_path = tmp_path / "config" / "article_scoring.local.yaml"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(
        yaml.dump(
            {"post_score_automation": {"auto_publish": {"enabled": True, "min_grade": "S"}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", local_path)

    save_auto_publish_settings(min_grade="A")
    assert get_auto_publish_settings()["min_grade"] == "A"


def test_save_media_pipeline_min_grade_persists_local(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "article_scoring.yaml"
    local_path = tmp_path / "config" / "article_scoring.local.yaml"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(
        yaml.dump(
            {
                "post_score_automation": {
                    "media_pipeline": {
                        "trigger": {"min_grade": "S", "min_score": 80, "logic": "or"},
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", local_path)

    save_media_pipeline_settings(min_grade="A")
    assert get_media_pipeline_settings()["min_grade"] == "A"


def test_save_media_pipeline_min_score_persists_local(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "article_scoring.yaml"
    local_path = tmp_path / "config" / "article_scoring.local.yaml"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(
        yaml.dump(
            {
                "post_score_automation": {
                    "media_pipeline": {
                        "trigger": {"min_grade": "S", "min_score": 80, "logic": "or"},
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", local_path)

    save_media_pipeline_settings(min_score=75, logic="or")
    settings = get_media_pipeline_settings()
    assert settings["min_score"] == 75.0
    assert settings["logic"] == "or"
