"""Fetch industry pack manifests from cloud Control Plane with bundled fallback."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from services.industry.config_loader import (
    PACKS_ROOT,
    local_l1_defaults_path,
    local_l2_pack_path,
    local_packs_root,
    resolve_l2_pack_path,
)
from services.industry.constants import is_valid_industry_id

__all__ = [
    "fetch_pack_manifest",
    "persist_pack_manifest",
    "apply_cloud_manifest_to_cache",
    "local_l2_pack_path",
    "local_packs_root",
]


def _bundled_manifest(industry_id: str) -> dict[str, Any]:
    pack_path = resolve_l2_pack_path(industry_id)
    if not pack_path.is_file():
        l1, l2 = industry_id.split("/", 1)
        pack_path = PACKS_ROOT / l1 / f"{l2}.yaml"
    if not pack_path.is_file():
        raise FileNotFoundError(f"No bundled pack for {industry_id}")
    content = pack_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(content) or {}
    industry = doc.get("industry") or {}
    l1, _ = industry_id.split("/", 1)
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
            payload.setdefault("path", industry_id)
            return payload
    except (urllib.error.URLError, ValueError, TypeError, json.JSONDecodeError, OSError):
        pass
    return _bundled_manifest(industry_id)


def persist_pack_manifest(manifest: dict[str, Any]) -> dict[str, Path]:
    """Write cloud manifest YAML (and optional L1 defaults) under data/cache/packs."""
    industry_id = str(manifest.get("path") or manifest.get("industry_id") or "").strip()
    if not is_valid_industry_id(industry_id):
        raise ValueError(f"Invalid manifest path: {industry_id}")
    content_yaml = manifest.get("content_yaml")
    if not isinstance(content_yaml, str) or not content_yaml.strip():
        raise ValueError("manifest content_yaml is required")

    l1, l2 = industry_id.split("/", 1)
    pack_dir = local_packs_root() / l1
    pack_dir.mkdir(parents=True, exist_ok=True)
    l2_path = pack_dir / f"{l2}.yaml"
    l2_path.write_text(content_yaml if content_yaml.endswith("\n") else content_yaml + "\n", encoding="utf-8")

    l1_defaults_yaml = manifest.get("l1_defaults_yaml")
    if isinstance(l1_defaults_yaml, str) and l1_defaults_yaml.strip():
        defaults_path = pack_dir / "_defaults.yaml"
        defaults_path.write_text(
            l1_defaults_yaml if l1_defaults_yaml.endswith("\n") else l1_defaults_yaml + "\n",
            encoding="utf-8",
        )

    meta_path = pack_dir / f"{l2}.manifest.json"
    meta = {
        "path": industry_id,
        "pack_version": manifest.get("pack_version"),
        "content_hash": manifest.get("content_hash"),
        "updated_at": manifest.get("updated_at"),
        "l1_defaults_key": manifest.get("l1_defaults_key"),
        "source": manifest.get("source", "cloud"),
        "persisted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"l2": l2_path, "meta": meta_path}


def apply_cloud_manifest_to_cache(industry_id: str) -> dict[str, Any]:
    """Download manifest, persist when from cloud, rebuild effective cache."""
    from services.industry.config_loader import refresh_effective_cache

    manifest = fetch_pack_manifest(industry_id)
    if manifest.get("source") == "cloud":
        persist_pack_manifest(manifest)
    return refresh_effective_cache(industry_id)
