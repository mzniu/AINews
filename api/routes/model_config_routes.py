"""Model configuration API (language + vision)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.model_config_models import ModelsConfigIn, ModelTestResponse
from services.model_config.registry import (
    merge_incoming_config,
    public_config,
    save_models_config,
    test_language_model,
    test_vision_model,
)

router = APIRouter(prefix="/api/models", tags=["模型配置"])


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
