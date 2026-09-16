"""Metrics sync configuration."""
from __future__ import annotations

from typing import Any

from services.publishing.registry import load_publishing_yaml


def load_metrics_sync_config() -> dict[str, Any]:
    defaults = load_publishing_yaml().get("defaults") or {}
    cfg = dict(defaults.get("metrics_sync") or {})
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "cron": str(cfg.get("cron", "0 6 * * *")),
        "since_days": int(cfg.get("since_days", 90)),
        "per_account_delay_sec": float(cfg.get("per_account_delay_sec", 8)),
        "max_posts_per_account": int(cfg.get("max_posts_per_account", 100)),
        "fuzzy_match_hours": int(cfg.get("fuzzy_match_hours", 24)),
        "alert_view_drop_pct": float(cfg.get("alert_view_drop_pct", 30)),
        "alert_min_previous_views": int(cfg.get("alert_min_previous_views", 100)),
    }
