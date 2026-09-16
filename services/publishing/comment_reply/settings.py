"""Comment reply toggle (publish center)."""
from __future__ import annotations

from typing import Any

import yaml

from services.publishing.comment_reply.config import load_comment_reply_config
from services.publishing.registry import load_publishing_yaml
from src.utils.config import Config

PUBLISHING_LOCAL_PATH = Config.CONFIG_DIR / "publishing_platforms.local.yaml"


def _load_yaml(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def get_comment_reply_settings() -> dict[str, Any]:
    cfg = load_comment_reply_config()
    local = _load_yaml(PUBLISHING_LOCAL_PATH).get("defaults") or {}
    local_cr = local.get("comment_reply") or {}
    if "enabled" in local_cr:
        cfg["enabled"] = bool(local_cr["enabled"])
    cfg["local_config_path"] = str(PUBLISHING_LOCAL_PATH)
    cfg["has_local_override"] = PUBLISHING_LOCAL_PATH.exists()
    return cfg


def save_comment_reply_settings(
    *,
    enabled: bool | None = None,
    mode: str | None = None,
    lookback_hours: int | None = None,
) -> dict[str, Any]:
    local = _load_yaml(PUBLISHING_LOCAL_PATH)
    defaults = local.setdefault("defaults", {})
    cr = defaults.setdefault("comment_reply", {})
    if enabled is not None:
        cr["enabled"] = bool(enabled)
    if mode is not None:
        normalized = str(mode).strip().lower()
        if normalized not in {"approve", "auto", "inline"}:
            raise ValueError("mode must be approve, auto, or inline")
        cr["mode"] = normalized
    if lookback_hours is not None:
        hours = int(lookback_hours)
        if hours < 1 or hours > 168:
            raise ValueError("lookback_hours must be between 1 and 168")
        cr["lookback_hours"] = hours
    PUBLISHING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLISHING_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return get_comment_reply_settings()
