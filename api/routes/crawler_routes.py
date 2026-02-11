"""爬虫相关API路由"""
from fastapi import APIRouter, HTTPException
from typing import Dict
from loguru import logger
from ..schemas.request_models import (
    FetchRequest, FetchResponse, GenerateSummaryRequest,
    GenerateImageRequest, ProcessImageRequest
)
from services.crawler_service import CrawlerService

router = APIRouter(prefix="/api", tags=["爬虫"])

@router.post("/fetch-url", response_model=FetchResponse)
async def fetch_url(request: FetchRequest):
    """抓取指定URL的内容"""
    try:
        html, title = await CrawlerService.get_page_content(str(request.url))
        content_data = CrawlerService.extract_content(html, str(request.url))
        metadata = CrawlerService.save_results(str(request.url), title, content_data['content'], content_data['images'])
        
        return FetchResponse(
            success=True,
            message="抓取成功",
            data=metadata
        )
    except Exception as e:
        logger.error(f"抓取失败: {e}")
        raise HTTPException(status_code=500, detail=f"抓取失败: {str(e)}")

@router.post("/generate-summary")
async def generate_summary(request: GenerateSummaryRequest):
    """生成AI摘要（模拟实现）"""
    try:
        # 这里应该调用真实的AI服务
        summary = f"根据提供的内容，这是一篇关于{request.title or '相关内容'}的文章摘要..."
        keywords = ["AI", "技术", "发展"]
        
        return {
            "success": True,
            "title": request.title or "AI资讯摘要",
            "summary": summary,
            "keywords": keywords,
            "word_count": len(summary)
        }
    except Exception as e:
        logger.error(f"生成摘要失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成摘要失败: {str(e)}")

@router.post("/generate-image")
async def generate_image(request: GenerateImageRequest):
    """生成视频关键帧"""
    try:
        from ...services.video_service import VideoService
        result = VideoService.create_video_frames(
            request.title, 
            request.summary, 
            request.images
        )
        return result
    except Exception as e:
        logger.error(f"生成关键帧失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成关键帧失败: {str(e)}")

@router.post("/process-image")
async def process_image(request: ProcessImageRequest):
    """处理图片（增强、锐化等）"""
    try:
        # 这里实现具体的图片处理逻辑
        return {
            "success": True,
            "message": f"图片{request.effect}处理完成",
            "processed_path": request.image_path
        }
    except Exception as e:
        logger.error(f"图片处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"图片处理失败: {str(e)}")