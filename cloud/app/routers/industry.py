from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_auth
from app.services.industry_catalog import get_pack_manifest as load_pack_manifest
from app.services.industry_catalog import load_taxonomy_yaml

router = APIRouter(prefix="/industry", tags=["industry"])


@router.get("/taxonomy")
def get_industry_taxonomy(
    _ctx=Depends(require_auth),
) -> dict[str, Any]:
    data = load_taxonomy_yaml()
    return {
        "schema_version": data.get("schema_version", 1),
        "l1": data.get("l1") or [],
    }


pack_router = APIRouter(tags=["industry-packs"])


@pack_router.get("/industry-packs/{industry_path:path}/manifest")
def read_pack_manifest(
    industry_path: str,
    db: Session = Depends(get_db),
    _ctx=Depends(require_auth),
) -> dict[str, Any]:
    normalized = industry_path.strip().strip("/")
    manifest = load_pack_manifest(db, normalized)
    if manifest is None:
        raise HTTPException(status_code=404, detail="pack not found")
    return manifest
