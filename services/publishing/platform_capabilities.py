"""Platform capability helpers from publishing_platforms.yaml."""
from __future__ import annotations

from services.publishing.registry import get_platform_config


def get_capabilities(platform_id: str) -> dict:
    cfg = get_platform_config(platform_id)
    return dict(cfg.get("capabilities") or {})


def can_account_login(platform_id: str) -> bool:
    return bool(get_capabilities(platform_id).get("account_login"))


def can_video_publish(platform_id: str) -> bool:
    return bool(get_capabilities(platform_id).get("video_publish"))


def get_platform_limits(platform_id: str) -> dict:
    cfg = get_platform_config(platform_id)
    return dict(cfg.get("limits") or {})
