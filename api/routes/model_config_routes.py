"""Model configuration API (language + vision)."""
from __future__ import annotations

from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.schemas.model_config_models import ModelsConfigIn, ModelTestResponse
from services.model_config.registry import (
    load_models_config,
    merge_incoming_config,
    public_config,
    save_models_config,
    test_language_model,
    test_vision_model,
)
from src.db.engine import get_session_factory

router = APIRouter(prefix="/api/models", tags=["模型配置"])


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


def _enrich_display_names(summary: dict[str, Any]) -> dict[str, Any]:
    cfg = load_models_config(migrate_env=False)
    names: dict[tuple[str, str | None], str] = {}
    for kind in ("language", "vision"):
        for profile in (cfg.get(kind) or {}).get("profiles") or []:
            pid = profile.get("id")
            if not pid:
                continue
            names[(kind, str(pid))] = str(profile.get("display_name") or profile.get("model") or pid)
    for row in summary.get("by_model") or []:
        name = names.get((row.get("kind"), row.get("profile_id")))
        if name:
            row["display_name"] = name
    return summary


@router.get("/config")
def get_models_config():
    return {"success": True, **public_config()}


@router.put("/config")
def update_models_config(body: ModelsConfigIn):
    try:
        merged = merge_incoming_config(body.model_dump())
        save_models_config(merged)
        return {"success": True, "message": "模型配置已保存", **public_config(merged)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test/language", response_model=ModelTestResponse)
def test_language():
    result = test_language_model()
    return ModelTestResponse(**result)


@router.post("/test/vision", response_model=ModelTestResponse)
def test_vision():
    result = test_vision_model()
    return ModelTestResponse(**result)


@router.get("/usage")
def get_model_usage(
    range: str = Query("7d", alias="range"),
    db: Session = Depends(get_db),
):
    from services.model_config.token_usage import query_token_usage

    try:
        summary = query_token_usage(db, range_key=range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "range": range, **_enrich_display_names(summary)}


@router.post("/usage/clear")
def clear_model_usage(db: Session = Depends(get_db)):
    from services.model_config.token_usage import clear_token_usage

    deleted = clear_token_usage(db)
    return {"success": True, "deleted": deleted}
