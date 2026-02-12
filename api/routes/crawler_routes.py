"""爬虫相关API路由"""
from fastapi import APIRouter, HTTPException
from typing import Dict
from loguru import logger
from ..schemas.request_models import (
    FetchRequest, FetchResponse, GenerateSummaryRequest,
    GenerateImageRequest, ProcessImageRequest
)
from services.crawler_service import CrawlerService
import os
import json
from openai import OpenAI

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
    """生成AI摘要"""
    try:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key or api_key == "your_deepseek_api_key_here":
            return {"success": False, "message": "请在.env文件中配置DEEPSEEK_API_KEY"}
        
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        prompt = f"""请为以下文章生成适合短视频的主标题、副标题、摘要和标签，要求：
1. 主标题：8-15字，一句话点明核心看点，简短有力，不使用任何emoji表情
   - 突出文章的核心价值和亮点
   - 使用具体的数据、成果或创新点
   - 避免过度夸张的对比（如"碾压GPT-4"）
   - 用疑问/反问/感叹激发好奇心
   - 直击用户关心的实际问题
   - 保持专业性和可信度
2. 副标题：10-20字，补充主标题的信息，提供更多细节或悬念，不使用任何emoji表情
3. 摘要：50-70字，简洁有力，适合短视频口播解说，节奏感强
4. 标签：10个相关标签，每个标签以#开头，用空格分隔

原标题：{request.title}

正文：
{request.content[:3000]}

请按以下JSON格式返回：
{{
  "main_title": "主标题（8-15字，不含emoji）",
  "sub_title": "副标题（10-20字，不含emoji）",
  "summary": "生成的摘要（50-70字）",
  "tags": "#AI #人工智能 #科技 ... (10个标签)"
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是顶级自媒体爆款标题大师，精通短视频内容运营。你的标题总能引发强烈的点击冲动，既有信息量又有情绪张力。你擅长用最凝练的文字传递最大的信息密度和情绪冲击。绝对不使用任何emoji表情符号。请严格按照JSON格式返回结果。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        
        tags = result.get('tags', '')
        main_title = result.get('main_title', result.get('title', ''))
        sub_title = result.get('sub_title', '')
        # 组合标题供前端显示，用 | 分隔主副标题
        combined_title = f"{main_title}|{sub_title}" if sub_title else main_title
        logger.success(f"标题生成成功 - 主标题: {main_title}, 副标题: {sub_title}, 摘要: {len(result['summary'])}字")
        
        return {
            "success": True,
            "title": combined_title,
            "main_title": main_title,
            "sub_title": sub_title,
            "summary": result['summary'],
            "tags": tags,
            "tokens_used": response.usage.total_tokens,
            "model": "deepseek-chat"
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