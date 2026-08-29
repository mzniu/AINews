"""Tests for image scoring local overrides."""
from __future__ import annotations

import yaml

from services.ingestion.image_scoring_settings import (
    IMAGE_SCORING_BASE_PATH,
    IMAGE_SCORING_LOCAL_PATH,
    get_image_scoring_criteria_settings,
    load_merged_image_scoring_config,
    save_image_scoring_criteria_settings,
)


def _write_base(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "profile": "short_video_clip",
                "scorer_version": "1.3",
                "weights": {
                    "topic_relevance": 0.30,
                    "info_value": 0.18,
                    "visual_quality": 0.12,
                    "flash_fit": 0.18,
                    "cover_fit": 0.05,
                    "figure_prominence": 0.10,
                    "compliance": 0.07,
                },
                "grades": {"A": 80, "B": 60, "C": 40},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def test_save_custom_weights_persists_local(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "image_scoring.yaml"
    local_path = tmp_path / "config" / "image_scoring.local.yaml"
    _write_base(base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_LOCAL_PATH", local_path)

    settings = get_image_scoring_criteria_settings()
    assert settings["profile"] == "short_video_clip"
    assert settings["weights"]["topic_relevance"] == 0.30

    save_image_scoring_criteria_settings(
        profile="custom",
        weights={
            "topic_relevance": 0.40,
            "info_value": 0.15,
            "visual_quality": 0.10,
            "flash_fit": 0.15,
            "cover_fit": 0.05,
            "figure_prominence": 0.10,
            "compliance": 0.05,
        },
    )
    assert local_path.exists()
    merged = load_merged_image_scoring_config()
    assert merged["profile"] == "custom"
    assert abs(merged["weights"]["topic_relevance"] - 0.40) < 0.01


def test_save_preset_applies_weights(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "image_scoring.yaml"
    local_path = tmp_path / "config" / "image_scoring.local.yaml"
    _write_base(base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_LOCAL_PATH", local_path)

    save_image_scoring_criteria_settings(profile="figure_focus")
    settings = get_image_scoring_criteria_settings()
    assert settings["profile"] == "figure_focus"
    assert settings["weights"]["figure_prominence"] > settings["weights"]["cover_fit"]


def test_load_merged_used_by_image_scorer(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "image_scoring.yaml"
    local_path = tmp_path / "config" / "image_scoring.local.yaml"
    _write_base(base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_LOCAL_PATH", local_path)

    local_path.write_text(
        yaml.dump({"grades": {"A": 85, "B": 65, "C": 45}}, allow_unicode=True),
        encoding="utf-8",
    )

    from services.ingestion.image_scorer import load_image_scoring_config

    cfg = load_image_scoring_config()
    assert cfg["grades"]["A"] == 85
    assert cfg["weights"]["topic_relevance"] == 0.30


def test_save_prefer_gif_boost_persists_local(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "image_scoring.yaml"
    local_path = tmp_path / "config" / "image_scoring.local.yaml"
    _write_base(base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.image_scoring_settings.IMAGE_SCORING_LOCAL_PATH", local_path)

    settings = get_image_scoring_criteria_settings()
    assert settings["prefer_gif_boost"] is False
    assert settings["gif_boost_points"] == 25

    save_image_scoring_criteria_settings(prefer_gif_boost=True)
    settings = get_image_scoring_criteria_settings()
    assert settings["prefer_gif_boost"] is True
    merged = load_merged_image_scoring_config()
    assert merged["prefer_gif_boost"] is True
