"""First-comment toggle and timing settings (publish center)."""
from __future__ import annotations

from typing import Any

import yaml

from services.publishing.registry import load_publishing_yaml
from src.utils.config import Config

PUBLISHING_LOCAL_PATH = Config.CONFIG_DIR / "publishing_platforms.local.yaml"


def _load_yaml(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _merged_defaults() -> dict[str, Any]:
    data = load_publishing_yaml()
    defaults = data.get("defaults") or {}
    local = _load_yaml(PUBLISHING_LOCAL_PATH).get("defaults") or {}
    first_comment = dict(defaults.get("first_comment") or {})
    first_comment.update(local.get("first_comment") or {})
    return first_comment


def get_first_comment_settings() -> dict[str, Any]:
    fc = _merged_defaults()
    try:
        delay = int(fc.get("comment_delay_sec", 15))
    except (TypeError, ValueError):
        delay = 15
    try:
        wait_max = int(fc.get("comment_wait_max_sec", 60))
    except (TypeError, ValueError):
        wait_max = 60
    return {
        "enabled": bool(fc.get("enabled", False)),
        "comment_delay_sec": max(0, delay),
        "comment_wait_max_sec": max(15, wait_max),
        "retry_max": max(1, int(fc.get("retry_max", 3) or 3)),
        "local_config_path": str(PUBLISHING_LOCAL_PATH),
        "has_local_override": PUBLISHING_LOCAL_PATH.exists(),
    }


def save_first_comment_settings(*, enabled: bool | None = None) -> dict[str, Any]:
    local = _load_yaml(PUBLISHING_LOCAL_PATH)
    defaults = local.setdefault("defaults", {})
    fc = defaults.setdefault("first_comment", {})
    if enabled is not None:
        fc["enabled"] = bool(enabled)
    PUBLISHING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLISHING_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return get_first_comment_settings()
