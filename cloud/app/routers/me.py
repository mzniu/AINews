from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentContext, require_auth
from app.services.industry_profile import set_active_industry

router = APIRouter(tags=["me"])


class ActiveIndustryBody(BaseModel):
    active_industry_id: str = Field(..., min_length=3, max_length=128)


@router.get("/me")
def get_me(ctx: CurrentContext = Depends(require_auth)) -> dict[str, Any]:
    ws = ctx.workspace
    return {
        "usercenter_user_id": ctx.usercenter_user_id,
        "email": ctx.email,
        "workspace": {
            "id": ws.id,
            "type": ws.type,
            "name": ws.name,
        },
        "active_industry_id": ws.active_industry_id,
        "industry_selected_at": (
            ws.industry_selected_at.isoformat() if ws.industry_selected_at else None
        ),
    }


@router.put("/me/active-industry")
def put_active_industry(
    body: ActiveIndustryBody,
    ctx: CurrentContext = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = set_active_industry(db, ctx.workspace, body.active_industry_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
