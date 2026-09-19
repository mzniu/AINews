"""Bundled industry taxonomy and pack manifest stubs (M0b desktop / offline)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.industry.config_loader import (
    PACKS_ROOT,
    _load_yaml,
    load_effective_cache,
    local_l2_pack_path,
)
from services.industry.profile import (
    activate_industry_l2,
    get_declared_active_industry_id,
    load_industry_profile,
    needs_industry_onboarding,
)
from services.industry.taxonomy import find_l2

router = APIRouter(prefix="/api/industry", tags=["industry"])
me_router = APIRouter(prefix="/api/me", tags=["industry"])


class IndustryActivateBody(BaseModel):
    active_industry_id: str = Field(..., min_length=3, max_length=128)


def _me_industry_payload() -> dict[str, Any]:
    active = get_declared_active_industry_id()
    cached = load_effective_cache(active) if active else {}
    meta = find_l2(active) if active else None
    return {
        "active_industry_id": active,
        "display_name": meta.get("display_name") if meta else None,
        "pack_version": (cached or {}).get("pack_version") or (
            meta.get("pack_version") if meta else None
        ),
        "manifest_hash": (cached or {}).get("manifest_hash"),
        "status": meta.get("status") if meta else None,
        "needs_onboarding": needs_industry_onboarding(),
        "profile": load_industry_profile(),
    }


def _taxonomy_path() -> Path:
    return PACKS_ROOT / "taxonomy.yaml"


@me_router.put("/industry")
def put_my_industry(body: IndustryActivateBody) -> dict[str, Any]:
    try:
        activate_industry_l2(body.active_industry_id.strip(), complete_onboarding=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _me_industry_payload()


@me_router.post("/industry/switch")
def switch_my_industry(body: IndustryActivateBody) -> dict[str, Any]:
    try:
        activate_industry_l2(
            body.active_industry_id.strip(),
            complete_onboarding=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = _me_industry_payload()
    payload["restart_required"] = True
    payload["message"] = "切换垂类后请重启 Python 服务以加载新的 effective 配置。"
    return payload


@me_router.post("/industry/sync-pack")
def sync_my_industry_pack() -> dict[str, Any]:
    from services.industry.pack_client import apply_cloud_manifest_to_cache
    from services.industry.profile import get_active_industry_id

    active = get_active_industry_id()
    effective = apply_cloud_manifest_to_cache(active)
    cached = load_effective_cache(active) or {}
    return {
        "active_industry_id": active,
        "pack_version": effective.get("pack_version"),
        "manifest_hash": cached.get("manifest_hash"),
        "pack_path": str(local_l2_pack_path(active)),
    }


@me_router.get("/industry")
def get_my_industry() -> dict[str, Any]:
    return _me_industry_payload()


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
