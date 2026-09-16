"""Comment reply configuration."""
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


def load_comment_reply_config() -> dict[str, Any]:
    defaults = load_publishing_yaml().get("defaults") or {}
    local = _load_yaml(PUBLISHING_LOCAL_PATH).get("defaults") or {}
    cfg = dict(defaults.get("comment_reply") or {})
    cfg.update(local.get("comment_reply") or {})
    platforms = cfg.get("platforms") or ["wechat_channels"]
    if isinstance(platforms, str):
        platforms = [platforms]
    mode = str(cfg.get("mode", "approve"))
    max_new = max(1, int(cfg.get("max_new_replies_per_run", 30) or 30))
    max_auto = max(1, int(cfg.get("max_auto_replies_per_run", 10) or 10))
    max_replies_per_run = max(1, int(cfg.get("max_replies_per_run", max_new) or max_new))
    if mode == "auto" and "max_replies_per_run" not in cfg:
        max_replies_per_run = max_auto
    effective_mode = "inline" if mode in {"auto", "inline"} else "approve"
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "cron": str(cfg.get("cron", "0 * * * *")),
        "mode": mode,
        "effective_mode": effective_mode,
        "lookback_hours": max(1, int(cfg.get("lookback_hours", 48) or 48)),
        "max_scan_posts": max(1, int(cfg.get("max_scan_posts", 30) or 30)),
        "max_new_replies_per_run": max_new,
        "max_auto_replies_per_run": max_auto,
        "max_replies_per_run": max_replies_per_run,
        "max_replies_per_post": max(1, int(cfg.get("max_replies_per_post", 20) or 20)),
        "pause_between_replies_sec": max(0, int(cfg.get("pause_between_replies_sec", 3) or 3)),
        "retry_enabled": bool(cfg.get("retry_enabled", True)),
        "retry_max": max(0, int(cfg.get("retry_max", 3) or 3)),
        "retry_batch_size": max(1, int(cfg.get("retry_batch_size", 10) or 10)),
        "reply_min_length": max(1, int(cfg.get("reply_min_length", 5) or 5)),
        "reply_max_length": max(10, int(cfg.get("reply_max_length", 50) or 50)),
        "platforms": [str(item).strip() for item in platforms if str(item).strip()],
    }