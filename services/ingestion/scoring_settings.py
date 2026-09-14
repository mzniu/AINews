"""Article scoring config: base YAML + local overrides (runtime toggles)."""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from services.ingestion.article_scorer import VALID_GRADES
from src.utils.config import Config

SCORING_BASE_PATH = Config.ROOT_DIR / "config" / "article_scoring.yaml"
SCORING_LOCAL_PATH = Config.CONFIG_DIR / "article_scoring.local.yaml"
SCORING_LEGACY_LOCAL_PATH = Config.ROOT_DIR / "config" / "article_scoring.local.yaml"


def _migrate_legacy_local_config() -> None:
    target = SCORING_LOCAL_PATH
    legacy = SCORING_LEGACY_LOCAL_PATH
    if target == legacy or target.exists() or not legacy.is_file():
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        with os.fdopen(fd, "wb") as destination, open(legacy, "rb") as source:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        try:
            os.link(temp_path, target)
        except FileExistsError:
            pass
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_local_yaml() -> dict[str, Any]:
    _migrate_legacy_local_config()
    return _load_yaml(SCORING_LOCAL_PATH)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_merged_scoring_config() -> dict[str, Any]:
    base = _load_yaml(SCORING_BASE_PATH)
    local = _load_local_yaml()
    if not local:
        return base
    return _deep_merge(base, local)


def get_auto_publish_settings() -> dict[str, Any]:
    cfg = load_merged_scoring_config()
    auto_publish = (cfg.get("post_score_automation") or {}).get("auto_publish") or {}
    min_grade = str(auto_publish.get("min_grade", "S")).upper()
    if min_grade not in VALID_GRADES:
        min_grade = "S"
    qh = auto_publish.get("quiet_hours") or {}
    try:
        interval = int(auto_publish.get("interval_minutes", 60))
    except (TypeError, ValueError):
        interval = 60
    interval = min(240, max(15, interval))
    return {
        "enabled": bool(auto_publish.get("enabled", True)),
        "skip_if_exists": bool(auto_publish.get("skip_if_exists", True)),
        "min_grade": min_grade,
        "interval_minutes": interval,
        "quiet_hours_enabled": bool(qh.get("enabled", False)),
        "quiet_hours_start": str(qh.get("start") or "23:00"),
        "quiet_hours_end": str(qh.get("end") or "07:00"),
        "grade_options": ["S", "A", "B", "C"],
        "local_config_path": str(SCORING_LOCAL_PATH),
        "has_local_override": SCORING_LOCAL_PATH.exists(),
    }


def _validate_hhmm(value: str) -> str:
    from services.publishing.schedule import _parse_hhmm as parse_hhmm

    parse_hhmm(value)
    return str(value).strip()


def save_auto_publish_settings(
    *,
    enabled: bool | None = None,
    min_grade: str | None = None,
    interval_minutes: int | None = None,
    quiet_hours_enabled: bool | None = None,
    quiet_hours_start: str | None = None,
    quiet_hours_end: str | None = None,
) -> dict[str, Any]:
    local = _load_local_yaml()
    post = local.setdefault("post_score_automation", {})
    auto = post.setdefault("auto_publish", {})
    qh = auto.setdefault("quiet_hours", {})
    quiet_changed = False
    if enabled is not None:
        auto["enabled"] = bool(enabled)
    if min_grade is not None:
        normalized = str(min_grade).strip().upper()
        if normalized not in VALID_GRADES:
            raise ValueError(f"无效等级: {min_grade}，可选 S/A/B/C/D")
        auto["min_grade"] = normalized
    if interval_minutes is not None:
        value = int(interval_minutes)
        if value < 15 or value > 240:
            raise ValueError("interval_minutes 须在 15–240 之间")
        auto["interval_minutes"] = value
    if quiet_hours_enabled is not None:
        qh["enabled"] = bool(quiet_hours_enabled)
        quiet_changed = True
    if quiet_hours_start is not None:
        qh["start"] = _validate_hhmm(quiet_hours_start)
        quiet_changed = True
    if quiet_hours_end is not None:
        qh["end"] = _validate_hhmm(quiet_hours_end)
        quiet_changed = True
    if qh.get("enabled"):
        from services.publishing.schedule import _parse_hhmm

        if _parse_hhmm(str(qh.get("start") or "23:00")) == _parse_hhmm(str(qh.get("end") or "07:00")):
            raise ValueError("禁发开始与结束时间不能相同")
    SCORING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORING_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    if quiet_changed and qh.get("enabled"):
        from src.db.engine import get_session_factory
        from services.publishing.schedule import load_spacing_config, reshuffle_jobs_in_quiet_window

        spacing = load_spacing_config(load_merged_scoring_config())
        with get_session_factory()() as session:
            reshuffle_jobs_in_quiet_window(session, config=spacing)
            session.commit()
    return get_auto_publish_settings()


def set_auto_publish_enabled(enabled: bool) -> dict[str, Any]:
    return save_auto_publish_settings(enabled=enabled)


def get_media_pipeline_settings() -> dict[str, Any]:
    cfg = load_merged_scoring_config()
    post = cfg.get("post_score_automation") or {}
    pipeline = post.get("media_pipeline") or {}
    trigger = pipeline.get("trigger") or {}
    min_grade = str(trigger.get("min_grade", "S")).upper()
    if min_grade not in VALID_GRADES:
        min_grade = "S"
    logic = str(trigger.get("logic", "or")).lower()
    if logic not in {"or", "and"}:
        logic = "or"
    return {
        "enabled": bool(post.get("enabled", True) and pipeline.get("enabled", True)),
        "min_grade": min_grade,
        "min_score": float(trigger.get("min_score", 80)),
        "logic": logic,
        "grade_options": ["S", "A", "B", "C"],
        "local_config_path": str(SCORING_LOCAL_PATH),
        "has_local_override": SCORING_LOCAL_PATH.exists(),
    }


def save_media_pipeline_settings(
    *,
    min_grade: str | None = None,
    min_score: float | None = None,
    logic: str | None = None,
) -> dict[str, Any]:
    local = _load_local_yaml()
    post = local.setdefault("post_score_automation", {})
    pipeline = post.setdefault("media_pipeline", {})
    trigger = pipeline.setdefault("trigger", {})
    if min_grade is not None:
        normalized = str(min_grade).strip().upper()
        if normalized not in VALID_GRADES:
            raise ValueError(f"无效等级: {min_grade}，可选 S/A/B/C/D")
        trigger["min_grade"] = normalized
    if min_score is not None:
        score = float(min_score)
        if score < 0 or score > 100:
            raise ValueError("min_score 须在 0–100 之间")
        trigger["min_score"] = score
    if logic is not None:
        normalized_logic = str(logic).strip().lower()
        if normalized_logic not in {"or", "and"}:
            raise ValueError("logic 仅支持 or / and")
        trigger["logic"] = normalized_logic
    SCORING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORING_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return get_media_pipeline_settings()


def get_scoring_criteria_settings() -> dict[str, Any]:
    from services.ingestion.scoring_presets import (
        DEFAULT_GRADES,
        detect_preset_id,
        dimension_catalog,
        merge_grades_from_config,
        merge_weights_from_config,
        preset_catalog,
    )

    cfg = load_merged_scoring_config()
    local = _load_local_yaml()
    weights = merge_weights_from_config(cfg)
    grades = merge_grades_from_config(cfg)
    profile = str(local.get("profile") or detect_preset_id(weights))
    if profile != "custom" and profile not in {p["id"] for p in preset_catalog()}:
        profile = detect_preset_id(weights)
    return {
        "profile": profile,
        "weights": weights,
        "grades": grades,
        "dimensions": dimension_catalog(),
        "presets": preset_catalog(),
        "weight_sum": round(sum(weights.values()), 4),
        "default_grades": dict(DEFAULT_GRADES),
        "local_config_path": str(SCORING_LOCAL_PATH),
        "has_local_override": SCORING_LOCAL_PATH.exists(),
    }


def save_scoring_criteria_settings(
    *,
    profile: str | None = None,
    weights: dict[str, Any] | None = None,
    grades: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from services.ingestion.scoring_presets import (
        SCORING_PRESETS,
        merge_grades_from_config,
        merge_weights_from_config,
        normalize_weights,
        validate_grades,
    )

    local = _load_local_yaml()
    merged = load_merged_scoring_config()

    next_weights = merge_weights_from_config(merged)
    next_grades = merge_grades_from_config(merged)

    if profile is not None:
        preset_id = str(profile).strip()
        if preset_id == "custom":
            local["profile"] = "custom"
        elif preset_id in SCORING_PRESETS:
            preset = SCORING_PRESETS[preset_id]
            next_weights = normalize_weights(preset["weights"], strict=False)
            next_grades = validate_grades(preset.get("grades") or next_grades)
            local["profile"] = preset_id
        else:
            raise ValueError(f"未知评分预设: {profile}")

    if weights is not None:
        next_weights = normalize_weights(weights, strict=True)
        local["profile"] = "custom"

    if grades is not None:
        next_grades = validate_grades(grades)

    local["weights"] = next_weights
    local["grades"] = next_grades
    SCORING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORING_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return get_scoring_criteria_settings()


def get_publish_policy_settings() -> dict[str, Any]:
    cfg = load_merged_scoring_config()
    policy = copy.deepcopy(cfg.get("publish_policy") or {})
    platforms = policy.get("platforms") or {}
    return {
        "policy_version": str(policy.get("policy_version", cfg.get("policy_version", 1))),
        "enabled": bool(policy.get("enabled", False)),
        "shadow_mode": bool(policy.get("shadow_mode", True)),
        "rollout": copy.deepcopy(policy.get("rollout") or {}),
        "platforms": copy.deepcopy(platforms),
        "local_config_path": str(SCORING_LOCAL_PATH),
        "has_local_override": SCORING_LOCAL_PATH.exists(),
    }


def save_publish_policy_settings(patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deep-merge publish_policy overrides into the writable local YAML."""
    local = _load_local_yaml()
    policy = local.setdefault("publish_policy", {})
    if patch:
        local["publish_policy"] = _deep_merge(policy, copy.deepcopy(patch))
    SCORING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORING_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return get_publish_policy_settings()
