"""Render template CRUD API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/ingestion", tags=["成片模板"])


@router.get("/render-templates")
def list_render_templates_route():
    from services.ingestion.render_templates import list_render_templates

    return {"success": True, **list_render_templates()}


@router.get("/render-templates/{template_id}")
def get_render_template_route(template_id: str):
    from services.ingestion.render_templates import get_render_template

    try:
        return {"success": True, "template": get_render_template(template_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/render-templates/default")
def set_default_render_template_route(body: dict):
    from services.ingestion.render_templates import set_default_template_id

    template_id = str((body or {}).get("template_id") or "").strip()
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id 必填")
    try:
        listed = set_default_template_id(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "message": "已设为默认成片模板", **listed}


@router.put("/render-templates/{template_id}")
def save_render_template_route(template_id: str, body: dict):
    from services.ingestion.render_templates import save_render_template

    try:
        template = save_render_template(template_id, body or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "template": template}


@router.post("/render-templates/{template_id}/duplicate")
def duplicate_render_template_route(template_id: str, body: dict | None = None):
    from services.ingestion.render_templates import duplicate_render_template

    payload = body or {}
    new_id = str(payload.get("new_id") or f"{template_id}_copy").strip()
    label = payload.get("label")
    try:
        template = duplicate_render_template(template_id, new_id=new_id, label=label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "template": template}


@router.delete("/render-templates/{template_id}")
def delete_render_template_route(template_id: str):
    from services.ingestion.render_templates import delete_render_template

    try:
        listed = delete_render_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **listed}
