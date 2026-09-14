"""Image scoring config: base YAML + local overrides."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

IMAGE_SCORING_BASE_PATH = Config.ROOT_DIR / "config" / "image_scoring.yaml"
IMAGE_SCORING_LOCAL_PATH = Config.CONFIG_DIR / "image_scoring.local.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_merged_image_scoring_config() -> dict[str, Any]:
    base = _load_yaml(IMAGE_SCORING_BASE_PATH)
    local = _load_yaml(IMAGE_SCORING_LOCAL_PATH)
    if not local:
        return base
    return _deep_merge(base, local)


def get_image_scoring_criteria_settings() -> dict[str, Any]:
    from services.ingestion.image_scoring_presets import (
        DEFAULT_GRADES,
        detect_preset_id,
        dimension_catalog,
        merge_grades_from_config,
        merge_weights_from_config,
        preset_catalog,
    )

    cfg = load_merged_image_scoring_config()
    local = _load_yaml(IMAGE_SCORING_LOCAL_PATH)
    weights = merge_weights_from_config(cfg)
    grades = merge_grades_from_config(cfg)
    profile = str(local.get("profile") or cfg.get("profile") or detect_preset_id(weights))
    if profile != "custom" and profile not in {p["id"] for p in preset_catalog()}:
        profile = detect_preset_id(weights)
    bonus_cfg = cfg.get("bonuses") or {}
    return {
        "profile": profile,
        "weights": weights,
        "grades": grades,
        "prefer_gif_boost": bool(cfg.get("prefer_gif_boost", False)),
        "gif_boost_points": float(bonus_cfg.get("gif_boost", 25)),
        "animated_bonus": float(bonus_cfg.get("animated", 8)),
        "dimensions": dimension_catalog(),
        "presets": preset_catalog(),
        "weight_sum": round(sum(weights.values()), 4),
        "default_grades": dict(DEFAULT_GRADES),
        "scorer_version": str(cfg.get("scorer_version") or ""),
        "local_config_path": str(IMAGE_SCORING_LOCAL_PATH),
        "has_local_override": IMAGE_SCORING_LOCAL_PATH.exists(),
    }


def save_image_scoring_criteria_settings(
    *,
    profile: str | None = None,
    weights: dict[str, Any] | None = None,
    grades: dict[str, Any] | None = None,
    prefer_gif_boost: bool | None = None,
) -> dict[str, Any]:
    from services.ingestion.image_scoring_presets import (
        IMAGE_SCORING_PRESETS,
        merge_grades_from_config,
        merge_weights_from_config,
        normalize_weights,
        validate_grades,
    )

    local = _load_yaml(IMAGE_SCORING_LOCAL_PATH)
    merged = load_merged_image_scoring_config()

    next_weights = merge_weights_from_config(merged)
    next_grades = merge_grades_from_config(merged)

    if profile is not None:
        preset_id = str(profile).strip()
        if preset_id == "custom":
            local["profile"] = "custom"
        elif preset_id in IMAGE_SCORING_PRESETS:
            preset = IMAGE_SCORING_PRESETS[preset_id]
            next_weights = normalize_weights(preset["weights"], strict=False)
            next_grades = validate_grades(preset.get("grades") or next_grades)
            local["profile"] = preset_id
        else:
            raise ValueError(f"未知配图评分预设: {profile}")

    if weights is not None:
        next_weights = normalize_weights(weights, strict=True)
        local["profile"] = "custom"

    if grades is not None:
        next_grades = validate_grades(grades)

    if prefer_gif_boost is not None:
        local["prefer_gif_boost"] = bool(prefer_gif_boost)

    local["weights"] = next_weights
    local["grades"] = next_grades
    IMAGE_SCORING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(IMAGE_SCORING_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return get_image_scoring_criteria_settings()
