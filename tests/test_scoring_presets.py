"""Tests for scoring presets and criteria settings."""
from __future__ import annotations

import pytest
import yaml

from services.ingestion.scoring_presets import (
    DEFAULT_GRADES,
    SCORING_PRESETS,
    detect_preset_id,
    normalize_weights,
    validate_grades,
)
from services.ingestion.scoring_settings import (
    get_scoring_criteria_settings,
    save_scoring_criteria_settings,
)


def test_normalize_weights_scales_to_one():
    weights = normalize_weights(
        {
            "timeliness": 2,
            "prominence": 2,
            "event_tension": 2,
            "breakthrough": 2,
            "product_heat": 2,
            "relevance": 2,
            "data_signal": 0,
            "creatability": 0,
            "hot_radar": 0,
        }
    )
    assert abs(sum(weights.values()) - 1.0) < 0.001


def test_validate_grades_requires_descending_order():
    with pytest.raises(ValueError):
        validate_grades({"S": 70, "A": 80, "B": 55, "C": 40})


def test_detect_preset_flash_news():
    from services.ingestion.scoring_presets import DEFAULT_WEIGHTS

    assert detect_preset_id(DEFAULT_WEIGHTS) == "flash_news"


def test_default_flash_and_balanced_presets_use_calibrated_industry_grades():
    expected = {"S": 88, "A": 70, "B": 55, "C": 40}
    assert DEFAULT_GRADES == expected
    assert SCORING_PRESETS["flash_news"]["grades"] == expected
    assert SCORING_PRESETS["balanced"]["grades"] == expected


def test_save_scoring_preset_persists_local(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "article_scoring.yaml"
    local_path = tmp_path / "config" / "article_scoring.local.yaml"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(
        yaml.dump({"weights": {"timeliness": 0.2}, "grades": {"S": 85, "A": 70, "B": 55, "C": 40}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", local_path)

    save_scoring_criteria_settings(profile="product_focus")
    settings = get_scoring_criteria_settings()
    assert settings["profile"] == "product_focus"
    assert settings["weights"]["product_heat"] > settings["weights"]["timeliness"]


def test_save_custom_weights_marks_profile_custom(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "article_scoring.yaml"
    local_path = tmp_path / "config" / "article_scoring.local.yaml"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(yaml.dump({}), encoding="utf-8")
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", local_path)

    save_scoring_criteria_settings(
        profile="custom",
        weights={
            "timeliness": 0.28,
            "prominence": 0.10,
            "event_tension": 0.10,
            "breakthrough": 0.10,
            "product_heat": 0.10,
            "relevance": 0.10,
            "data_signal": 0.08,
            "creatability": 0.08,
            "hot_radar": 0.08,
        },
    )
    settings = get_scoring_criteria_settings()
    assert settings["profile"] == "custom"
    assert abs(settings["weights"]["timeliness"] - 0.28) < 0.03
