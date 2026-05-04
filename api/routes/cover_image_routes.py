"""AI 封面图：Seedance / 火山 Ark 文生图 + 入库到 data/local_uploads"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.routes.image_search_routes import api_import_remote_image
from api.schemas.request_models import GenerateCoverImageRequest, ImportRemoteImageRequest
from services.seedance_image_service import (
    build_cover_prompt_from_content,
    generate_cover_image_url,
)

router = APIRouter(prefix="/api", tags=["封面图"])


@router.post("/generate-cover-image")
async def api_generate_cover_image(body: GenerateCoverImageRequest) -> Dict[str, Any]:
    """
    根据正文（与可选标题）调用文生图 API，将结果下载到本地并返回与 /upload-local-image 一致的 image_path。
    需配置 SEEDANCE_API_KEY 或 ARK_API_KEY，以及（可选）SEEDANCE_IMAGE_API_URL、SEEDANCE_IMAGE_MODEL。
    """
    custom = (body.prompt or "").strip()
    if custom:
        prompt = custom[:2000]
    else:
        prompt = build_cover_prompt_from_content(
            body.content or "",
            body.title or "",
            body.extra_hint or "",
        )

    logger.info(f"封面生图 prompt 长度={len(prompt)}")

    gen = generate_cover_image_url(prompt)
    if not gen.get("success"):
        msg = gen.get("error") or "生图失败"
        raise HTTPException(status_code=503, detail=msg)

    image_url = gen["image_url"]
    saved = await api_import_remote_image(
        ImportRemoteImageRequest(
            url=image_url,
            referer="https://ark.volces.com/",
        )
    )
    if isinstance(saved, dict):
        saved["prompt_used"] = prompt
        saved["source_url"] = image_url
    return saved
