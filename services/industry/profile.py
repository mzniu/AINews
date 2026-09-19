"""Local mirror of the user's active L2 industry (desktop cache)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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


def _write_profile(payload: dict[str, Any]) -> None:
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _dev_mode_skips_onboarding() -> bool:
    return os.getenv("AINES_DEV_MODE", "").strip().lower() in {"1", "true", "yes"}


def needs_industry_onboarding() -> bool:
    if _dev_mode_skips_onboarding():
        return False
    profile = load_industry_profile()
    return not bool(profile.get("onboarding_completed"))


def get_active_industry_id() -> str:
    env = os.getenv("AINEWS_ACTIVE_INDUSTRY_ID", "").strip()
    if env and is_valid_industry_id(env):
        return env
    stored = load_industry_profile().get("active_industry_id")
    if isinstance(stored, str) and is_valid_industry_id(stored):
        return stored.strip()
    return DEFAULT_INDUSTRY_ID


def get_declared_active_industry_id() -> str | None:
    """Active L2 for API/UI; None until user completes onboarding selection."""
    if needs_industry_onboarding():
        stored = load_industry_profile().get("active_industry_id")
        if not (isinstance(stored, str) and is_valid_industry_id(stored)):
            return None
    return get_active_industry_id()


def _refresh_effective_for(active: str) -> None:
    if os.getenv("AINEWS_CLOUD_API_BASE", "").strip():
        from services.industry.pack_client import apply_cloud_manifest_to_cache

        apply_cloud_manifest_to_cache(active)
    else:
        from services.industry.config_loader import refresh_effective_cache

        refresh_effective_cache(active)


def save_industry_profile(active_industry_id: str) -> None:
    if not is_valid_industry_id(active_industry_id):
        raise ValueError(f"Invalid industry_id: {active_industry_id}")
    active = active_industry_id.strip()
    payload = dict(load_industry_profile())
    payload["active_industry_id"] = active
    _write_profile(payload)
    _refresh_effective_for(active)


def activate_industry_l2(
    active_industry_id: str,
    *,
    complete_onboarding: bool = True,
    sync_cloud: bool = True,
) -> dict[str, Any]:
    from services.industry.cloud_profile import put_cloud_active_industry
    from services.industry.taxonomy import find_l2

    if not is_valid_industry_id(active_industry_id):
        raise ValueError(f"Invalid industry_id: {active_industry_id}")
    meta = find_l2(active_industry_id)
    if meta is None:
        raise ValueError(f"Unknown industry_id: {active_industry_id}")

    active = active_industry_id.strip()
    payload = dict(load_industry_profile())
    payload["active_industry_id"] = active
    if complete_onboarding:
        payload["onboarding_completed"] = True
        payload["onboarding_completed_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
    _write_profile(payload)
    _refresh_effective_for(active)

    cloud_result: dict[str, Any] | None = None
    if sync_cloud:
        cloud_result = put_cloud_active_industry(active)
    return {"industry": meta, "cloud": cloud_result}
