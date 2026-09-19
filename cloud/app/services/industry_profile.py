from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.workspace import Workspace
from app.services.industry_catalog import get_pack_manifest, is_valid_industry_id, list_known_l2_paths


def set_active_industry(
    db: Session,
    workspace: Workspace,
    active_industry_id: str,
) -> dict:
    active = active_industry_id.strip()
    if not is_valid_industry_id(active):
        raise ValueError(f"Invalid industry_id: {active}")
    known = list_known_l2_paths()
    if known and active not in known:
        raise ValueError(f"Unknown industry_id: {active}")
    manifest = get_pack_manifest(db, active)
    if manifest is None:
        raise ValueError(f"Pack not found: {active}")

    workspace.active_industry_id = active
    workspace.industry_selected_at = datetime.now(timezone.utc)
    db.flush()
    return {
        "active_industry_id": active,
        "pack_version": manifest.get("pack_version"),
    }
