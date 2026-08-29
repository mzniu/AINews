"""Platform capability helpers from publishing_platforms.yaml."""
from __future__ import annotations

from services.publishing.registry import PlatformNotFoundError, get_platform_config


def get_capabilities(platform_id: str) -> dict:
    try:
        cfg = get_platform_config(platform_id)
    except PlatformNotFoundError:
        return {}
    return dict(cfg.get("capabilities") or {})

def can_account_login(platform_id: str) -> bool:
    return bool(get_capabilities(platform_id).get("account_login"))


def can_video_publish(platform_id: str) -> bool:
    return bool(get_capabilities(platform_id).get("video_publish"))


def can_post_first_comment(platform_id: str) -> bool:
    return bool(get_capabilities(platform_id).get("first_comment"))


def get_platform_limits(platform_id: str) -> dict:
    try:
        cfg = get_platform_config(platform_id)
    except PlatformNotFoundError:
        return {}
    return dict(cfg.get("limits") or {})