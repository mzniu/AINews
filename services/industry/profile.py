"""Local mirror of the user's active L2 industry (desktop cache)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.industry.constants import DEFAULT_INDUSTRY_ID, is_valid_industry_id
from src.utils.paths import get_data_dir

_PROFILE_FILENAME = "industry_profile.json"


def _profile_path() -> Path:
    return get_data_dir() / "cache" / _PROFILE_FILENAME


def load_industry_profile() -> dict[str, Any]:
    path = _profile_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_industry_profile(active_industry_id: str) -> None:
    if not is_valid_industry_id(active_industry_id):
        raise ValueError(f"Invalid industry_id: {active_industry_id}")
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"active_industry_id": active_industry_id.strip()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    import os

    active = active_industry_id.strip()
    if os.getenv("AINEWS_CLOUD_API_BASE", "").strip():
        from services.industry.pack_client import apply_cloud_manifest_to_cache

        apply_cloud_manifest_to_cache(active)
    else:
        from services.industry.config_loader import refresh_effective_cache

        refresh_effective_cache(active)


def get_active_industry_id() -> str:
    env = os.getenv("AINEWS_ACTIVE_INDUSTRY_ID", "").strip()
    if env and is_valid_industry_id(env):
        return env
    stored = load_industry_profile().get("active_industry_id")
    if isinstance(stored, str) and is_valid_industry_id(stored):
        return stored.strip()
    return DEFAULT_INDUSTRY_ID
