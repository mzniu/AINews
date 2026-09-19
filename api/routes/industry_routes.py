"""Bundled industry taxonomy and pack manifest stubs (M0b desktop / offline)."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Generator
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.ingestion.worker import get_ingestion_worker_mode
from src.db.engine import get_session_factory

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


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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


def _apply_industry_runtime_reload(
    request: Request,
    db: Session,
) -> dict[str, Any]:
    from services.industry.runtime_reload import reload_industry_runtime

    worker = getattr(request.app.state, "ingestion_worker", None)
    return reload_industry_runtime(db, worker)


@me_router.put("/industry")
def put_my_industry(
    body: IndustryActivateBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        activate_industry_l2(body.active_industry_id.strip(), complete_onboarding=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = _me_industry_payload()
    payload.update(_apply_industry_runtime_reload(request, db))
    return payload


@me_router.post("/industry/switch")
def switch_my_industry(
    body: IndustryActivateBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        activate_industry_l2(
            body.active_industry_id.strip(),
            complete_onboarding=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = _me_industry_payload()
    reload_meta = _apply_industry_runtime_reload(request, db)
    payload.update(reload_meta)
    if reload_meta.get("runtime_reloaded"):
        payload["message"] = "已切换垂类，抓取与热榜调度已自动刷新。"
    elif get_ingestion_worker_mode() == "separate":
        payload["message"] = "已切换垂类，独立 ingestion worker 将在数秒内刷新调度。"
    else:
        payload["message"] = "已切换垂类；内嵌 worker 未运行，请启动服务后生效。"
    return payload


@me_router.post("/industry/sync-pack")
def sync_my_industry_pack(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from services.industry.pack_client import apply_cloud_manifest_to_cache
    from services.industry.profile import get_active_industry_id

    active = get_active_industry_id()
    effective = apply_cloud_manifest_to_cache(active)
    cached = load_effective_cache(active) or {}
    payload = {
        "active_industry_id": active,
        "pack_version": effective.get("pack_version"),
        "manifest_hash": cached.get("manifest_hash"),
        "pack_path": str(local_l2_pack_path(active)),
    }
    payload.update(_apply_industry_runtime_reload(request, db))
    return payload


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
