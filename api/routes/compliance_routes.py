"""违禁词合规 API。"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from utils.content_compliance import scan_plain_text, validate_llm_result
from utils.forbidden_words import get_registry, reload_registry

router = APIRouter(prefix="/api/compliance", tags=["合规"])


class ComplianceCheckRequest(BaseModel):
    text: Optional[str] = Field(default=None, description="单字段待检文本")
    field: str = Field(default="summary", description="字段名，用于结果标注")
    fields: Optional[Dict[str, Any]] = Field(default=None, description="多字段待检内容")


class ComplianceCheckResponse(BaseModel):
    success: bool
    ok: bool
    violations: List[Dict[str, str]]


@router.get("/forbidden-words")
async def list_forbidden_words():
    """只读返回当前违禁词配置摘要。"""
    registry = get_registry()
    return {"success": True, "data": registry.summary_dict()}


@router.post("/reload")
async def reload_forbidden_words():
    """强制重载违禁词配置。"""
    registry = reload_registry()
    return {
        "success": True,
        "message": "违禁词配置已重载",
        "category_count": len(registry.enabled_categories()),
    }


@router.post("/check", response_model=ComplianceCheckResponse)
async def check_compliance(request: ComplianceCheckRequest):
    """手动校验文本或 AI 字段集合是否命中禁限词。"""
    registry = get_registry()
    if request.fields:
        result = validate_llm_result(request.fields, registry=registry)
        return ComplianceCheckResponse(
            success=True,
            ok=result.ok,
            violations=[item.to_dict() for item in result.violations],
        )

    text = (request.text or "").strip()
    if not text:
        return ComplianceCheckResponse(success=True, ok=True, violations=[])

    violations = scan_plain_text(text, field=request.field, registry=registry)
    errors = [item for item in violations if item.severity == "error"]
    return ComplianceCheckResponse(
        success=True,
        ok=not errors,
        violations=[item.to_dict() for item in violations],
    )
