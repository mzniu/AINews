"""全网相关图片补充 API。"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.schemas.request_models import RelatedImageCrawlRequest
from services.related_image_service import RelatedImageService

router = APIRouter(prefix="/api", tags=["相关图片"])


@router.post("/related-images/crawl")
async def crawl_related_images(body: RelatedImageCrawlRequest) -> Dict[str, Any]:
    """调用大模型生成搜索词，搜索相关网页并抓取图片。"""
    if not (body.title or body.content or body.query):
        raise HTTPException(status_code=400, detail="标题、正文或搜索词至少提供一项")

    try:
        return await RelatedImageService.collect_related_images(
            title=body.title,
            content=body.content,
            source_url=body.source_url,
            query=body.query,
            search_sources=body.search_sources,
            max_pages=body.max_pages,
            max_crawl_pages=body.max_crawl_pages,
            max_images_per_page=body.max_images_per_page,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(f"全网相关图片抓取失败: {exc}")
        raise HTTPException(status_code=500, detail=f"全网相关图片抓取失败: {exc}") from exc