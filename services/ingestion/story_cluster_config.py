"""Load story clustering configuration (rules + AI layers)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "title_threshold": 0.72,
    "hours_window": 72,
    "gray_low": 0.55,
    "embedding": {
        "enabled": True,
        "method": "hashing",
        "rule_weight": 0.55,
        "embedding_weight": 0.45,
        "embedding_model": "text-embedding-3-small",
        "dimensions": 256,
    },
    "llm": {
        "enabled": True,
        "gray_low": 0.55,
        "gray_high": 0.85,
        "min_confidence": 0.7,
    },
    "review": {
        "enabled": True,
        "scan_limit": 30,
        "merge_candidate_threshold": 0.62,
    },
}

_CONFIG_PATH = Config.ROOT_DIR / "config" / "ingestion_sources.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_story_cluster_config(override: dict[str, Any] | None = None) -> dict[str, Any]:
    active = dict(_DEFAULTS)
    if _CONFIG_PATH.exists():
        try:
            raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            defaults = raw.get("defaults") or {}
            story_cfg = defaults.get("story_cluster") or {}
            if isinstance(story_cfg, dict):
                active = _deep_merge(active, story_cfg)
        except (OSError, yaml.YAMLError):
            pass
    if override:
        active = _deep_merge(active, override)
    return active
