"""Tests for article scoring local overrides."""
from __future__ import annotations

import pytest
import yaml

from services.ingestion.scoring_settings import (
    SCORING_BASE_PATH,
    SCORING_LOCAL_PATH,
    get_auto_publish_settings,
    get_media_pipeline_settings,
    load_merged_scoring_config,
    save_auto_publish_settings,
    save_media_pipeline_settings,
    save_scoring_criteria_settings,
    set_auto_publish_enabled,
)
from src.utils.config import Config


SAVE_FIRST_CASES = [
    pytest.param(
        save_auto_publish_settings,
        {"min_grade": "A"},
        ("post_score_automation", "auto_publish", "min_grade"),
        "A",
        id="auto-publish-settings",
    ),
    pytest.param(
        set_auto_publish_enabled,
        {"enabled": True},
        ("post_score_automation", "auto_publish", "enabled"),
        True,
        id="auto-publish-enabled",
    ),
    pytest.param(
        save_media_pipeline_settings,
        {"min_score": 75},
        ("post_score_automation", "media_pipeline", "trigger", "min_score"),
        75.0,
        id="media-pipeline-settings",
    ),
    pytest.param(
        save_scoring_criteria_settings,
        {"grades": {"S": 90, "A": 72, "B": 55, "C": 40}},
        ("grades", "S"),
        90.0,
        id="scoring-criteria-settings",
    ),
]


def _nested_value(config, keys):
    value = config
    for key in keys:
        value = value[key]
    return value


def _write_save_first_configs(tmp_path, monkeypatch, *, writable=None):
    resource_config = tmp_path / "resources" / "config"
    base_path = resource_config / "article_scoring.yaml"
    legacy_local = resource_config / "article_scoring.local.yaml"
    writable_local = tmp_path / "appdata" / "data" / "config" / "article_scoring.local.yaml"
    resource_config.mkdir(parents=True)
    base_path.write_text("{}\n", encoding="utf-8")
    legacy = {
        "origin": "legacy",
        "legacy_only": {"preserved": True},
        "post_score_automation": {
            "auto_publish": {"enabled": False, "min_grade": "B", "skip_if_exists": False},
            "media_pipeline": {
                "trigger": {"min_grade": "A", "min_score": 65, "logic": "and"},
            },
        },
    }
    legacy_bytes = yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False).encode("utf-8")
    legacy_local.write_bytes(legacy_bytes)
    if writable is not None:
        writable_local.parent.mkdir(parents=True)
        writable_local.write_text(
            yaml.safe_dump(writable, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", writable_local)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LEGACY_LOCAL_PATH", legacy_local)
    return writable_local, legacy_local, legacy_bytes


def test_scoring_paths_keep_base_in_resources_and_local_in_writable_config():
    assert SCORING_BASE_PATH == Config.ROOT_DIR / "config" / "article_scoring.yaml"
    assert SCORING_LOCAL_PATH == Config.CONFIG_DIR / "article_scoring.local.yaml"


def test_load_migrates_legacy_resource_local_once(tmp_path, monkeypatch):
    resource_config = tmp_path / "resources" / "config"
    writable_local = tmp_path / "appdata" / "data" / "config" / "article_scoring.local.yaml"
    base_path = resource_config / "article_scoring.yaml"
    legacy_local = resource_config / "article_scoring.local.yaml"
    resource_config.mkdir(parents=True)
    base_path.write_text(
        yaml.safe_dump({"weights": {"timeliness": 0.1}, "profile": "base"}),
        encoding="utf-8",
    )
    legacy_bytes = yaml.safe_dump(
        {"weights": {"timeliness": 0.9}, "profile": "legacy"},
        allow_unicode=True,
    ).encode("utf-8")
    legacy_local.write_bytes(legacy_bytes)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", writable_local)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LEGACY_LOCAL_PATH", legacy_local)

    merged = load_merged_scoring_config()

    assert merged["profile"] == "legacy"
    assert merged["weights"]["timeliness"] == 0.9
    assert writable_local.read_bytes() == legacy_bytes
    legacy_local.write_text("profile: changed-after-migration\n", encoding="utf-8")
    assert load_merged_scoring_config()["profile"] == "legacy"
    assert writable_local.read_bytes() == legacy_bytes


def test_load_never_overwrites_existing_writable_local(tmp_path, monkeypatch):
    resource_config = tmp_path / "resources" / "config"
    writable_local = tmp_path / "appdata" / "data" / "config" / "article_scoring.local.yaml"
    base_path = resource_config / "article_scoring.yaml"
    legacy_local = resource_config / "article_scoring.local.yaml"
    resource_config.mkdir(parents=True)
    writable_local.parent.mkdir(parents=True)
    base_path.write_text("profile: base\n", encoding="utf-8")
    legacy_local.write_text("profile: legacy\n", encoding="utf-8")
    writable_bytes = b"profile: writable\n"
    writable_local.write_bytes(writable_bytes)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LOCAL_PATH", writable_local)
    monkeypatch.setattr("services.ingestion.scoring_settings.SCORING_LEGACY_LOCAL_PATH", legacy_local)

    merged = load_merged_scoring_config()

    assert merged["profile"] == "writable"
    assert writable_local.read_bytes() == writable_bytes


@pytest.mark.parametrize(("save", "kwargs", "updated_path", "updated_value"), SAVE_FIRST_CASES)
def test_save_first_migrates_legacy_before_read(
    tmp_path,
    monkeypatch,
    save,
    kwargs,
    updated_path,
    updated_value,
):
    writable_local, legacy_local, legacy_bytes = _write_save_first_configs(tmp_path, monkeypatch)

    save(**kwargs)

    saved = yaml.safe_load(writable_local.read_text(encoding="utf-8"))
    assert saved["origin"] == "legacy"
    assert saved["legacy_only"]["preserved"] is True
    assert _nested_value(saved, updated_path) == updated_value
    assert legacy_local.read_bytes() == legacy_bytes


@pytest.mark.parametrize(("save", "kwargs", "updated_path", "updated_value"), SAVE_FIRST_CASES)
def test_save_first_keeps_existing_writable_instead_of_legacy(
    tmp_path,
    monkeypatch,
    save,
    kwargs,
    updated_path,
    updated_value,
):
    existing = {
        "origin": "writable",
        "writable_only": {"preserved": True},
        "post_score_automation": {
            "auto_publish": {"enabled": False, "min_grade": "B"},
            "media_pipeline": {"trigger": {"min_grade": "A", "min_score": 65, "logic": "and"}},
        },
    }
    writable_local, _, _ = _write_save_first_configs(
        tmp_path,
        monkeypatch,
        writable=existing,
    )

    save(**kwargs)

    saved = yaml.safe_load(writable_local.read_text(encoding="utf-8"))
    assert saved["origin"] == "writable"
    assert saved["writable_only"]["preserved"] is True
    assert "legacy_only" not in saved
    assert _nested_value(saved, updated_path) == updated_value


def test_recovery_policy_scaffolding_is_disabled_by_default():
    config = yaml.safe_load(SCORING_BASE_PATH.read_text(encoding="utf-8"))

    assert config["policy_version"]
    assert config["industry_bonus"]["max_total_points"] == 8
    policy = config["publish_policy"]
    assert policy["enabled"] is False
    assert policy["shadow_mode"] is True
    assert policy["platforms"]["wechat_channels"]["daily_limit"] == 8
    assert policy["platforms"]["douyin"]["daily_limit"] == 10
    assert policy["platforms"]["kuaishou"]["daily_limit"] == 5
    assert policy["time_window"]["timezone"]
    assert policy["time_window"]["default_start"]
    assert policy["time_window"]["default_end"]


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
