"""Fetch industry pack manifests from cloud Control Plane with bundled fallback."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import yaml

from services.industry.config_loader import PACKS_ROOT, _load_yaml
from services.industry.constants import is_valid_industry_id


def _bundled_manifest(industry_id: str) -> dict[str, Any]:
    l1, l2 = industry_id.split("/", 1)
    pack_path = PACKS_ROOT / l1 / f"{l2}.yaml"
    if not pack_path.is_file():
        raise FileNotFoundError(f"No bundled pack for {industry_id}")
    content = pack_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(content) or {}
    industry = doc.get("industry") or {}
    return {
        "path": industry_id,
        "pack_version": industry.get("pack_version"),
        "content_yaml": content,
        "l1_defaults_key": f"packs/{l1}/_defaults.yaml",
        "updated_at": (doc.get("metadata") or {}).get("updated_at"),
        "source": "bundled",
    }


def fetch_pack_manifest(industry_id: str, *, timeout: float = 10.0) -> dict[str, Any]:
    if not is_valid_industry_id(industry_id):
        raise ValueError(f"Invalid industry_id: {industry_id}")
    base = os.getenv("AINEWS_CLOUD_API_BASE", "").strip().rstrip("/")
    if not base:
        return _bundled_manifest(industry_id)
    url = f"{base}/industry-packs/{industry_id}/manifest"
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("content_yaml"):
            payload["source"] = "cloud"
            return payload
    except (urllib.error.URLError, ValueError, TypeError, json.JSONDecodeError, OSError):
        pass
    return _bundled_manifest(industry_id)


def apply_cloud_manifest_to_cache(industry_id: str) -> dict[str, Any]:
    """Download manifest (cloud or bundled) and rebuild effective cache."""
    from services.industry.config_loader import refresh_effective_cache

    manifest = fetch_pack_manifest(industry_id)
    # M0b: bundled files remain source of truth for merge; cloud path reserved for M0c sync.
    _load_yaml(PACKS_ROOT / "taxonomy.yaml")
    return refresh_effective_cache(industry_id)
