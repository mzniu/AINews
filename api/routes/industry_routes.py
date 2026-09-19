"""Bundled industry taxonomy and pack manifest stubs (M0b desktop / offline)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from services.industry.config_loader import PACKS_ROOT, _load_yaml, load_effective_cache
from services.industry.profile import get_active_industry_id, load_industry_profile

router = APIRouter(prefix="/api/industry", tags=["industry"])
me_router = APIRouter(prefix="/api/me", tags=["industry"])


def _taxonomy_path() -> Path:
    return PACKS_ROOT / "taxonomy.yaml"


@me_router.get("/industry")
def get_my_industry() -> dict[str, Any]:
    active = get_active_industry_id()
    cached = load_effective_cache(active) or {}
    profile = load_industry_profile()
    return {
        "active_industry_id": active,
        "pack_version": cached.get("pack_version"),
        "manifest_hash": cached.get("manifest_hash"),
        "profile": profile,
    }


@router.get("/taxonomy")
def get_industry_taxonomy() -> dict[str, Any]:
    data = _load_yaml(_taxonomy_path())
    if not data:
        raise HTTPException(status_code=503, detail="taxonomy unavailable")
    return {
        "schema_version": data.get("schema_version", 1),
        "l1": data.get("l1") or [],
    }


@router.get("/packs/{industry_path:path}/manifest")
def get_pack_manifest(industry_path: str) -> dict[str, Any]:
    normalized = industry_path.strip().strip("/")
    if "/" not in normalized:
        raise HTTPException(status_code=400, detail="industry_path must be L2 path")
    l1, l2 = normalized.split("/", 1)
    pack_path = PACKS_ROOT / l1 / f"{l2}.yaml"
    if not pack_path.is_file():
        raise HTTPException(status_code=404, detail="pack not found")
    content = pack_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(content) or {}
    industry = doc.get("industry") or {}
    return {
        "path": normalized,
        "pack_version": industry.get("pack_version"),
        "content_yaml": content,
        "l1_defaults_key": f"packs/{l1}/_defaults.yaml",
        "updated_at": (doc.get("metadata") or {}).get("updated_at"),
    }
