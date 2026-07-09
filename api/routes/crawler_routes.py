"""爬虫相关API路由"""
import asyncio
from fastapi import APIRouter, HTTPException
from typing import Dict
from loguru import logger
from ..schemas.request_models import (
    FetchRequest, FetchResponse, GenerateSummaryRequest,
    GenerateImageRequest, ProcessImageRequest
)
from services.crawler_service import CrawlerService
from utils.tags_normalizer import normalize_structured_tags, DEFAULT_STRUCTURED_TAGS
import os
import json
import re
from openai import OpenAI

router = APIRouter(prefix="/api", tags=["爬虫"])


@router.post("/fetch-venturebeat", response_model=FetchResponse)
async def fetch_venturebeat(request: FetchRequest):
    """专门抓取VentureBeat文章内容"""
    try:
        # 检查是否为VentureBeat URL
        from urllib.parse import urlparse
        parsed_url = urlparse(str(request.url))
        if 'venturebeat.com' not in parsed_url.netloc:
            raise HTTPException(status_code=400, detail="该接口仅支持VentureBeat网站")
        
        logger.info(f"开始抓取VentureBeat文章: {request.url}")
        
        # 使用异步VentureBeat爬虫
        from services.async_article_crawler import crawl_venturebeat_article_async, AsyncArticleData
        
        article_data = await crawl_venturebeat_article_async(str(request.url))
        
        if not article_data:
            raise HTTPException(status_code=500, detail="抓取文章失败")
        
        # 下载图片
        from services.async_article_crawler import AsyncVentureBeatCrawler
        crawler = AsyncVentureBeatCrawler()
        downloaded_images = await crawler.download_images(article_data)
        article_data.downloaded_images = downloaded_images
        
        # 构造返回数据格式与现有接口一致
        from datetime import datetime
        metadata = {
            "url": article_data.url,
            "title": article_data.title,
            "author": article_data.author,
            "publish_time": article_data.publish_date,
            "content": article_data.content,
            "content_length": len(article_data.content),
            "content_preview": article_data.content[:500] + ("..." if len(article_data.content) > 500 else ""),
            "images": [{"url": img['url'], "success": True} for img in article_data.images],  # 图片已经下载成功
            "images_count": len(article_data.images),
            "videos": [],  # VentureBeat文章通常没有视频
            "videos_count": 0,
            "tags": article_data.tags,
            "crawl_time": datetime.now().isoformat(),
            "source": "VentureBeat",
            "summary": article_data.summary
        }
        
        # 保存结果到文件系统（不重复下载图片，因为我们已经在异步爬虫中下载过了）
        from services.crawler_service import CrawlerService
        saved_metadata = CrawlerService.save_results(
            str(request.url),
            article_data.title,
            article_data.content,
            [],  # 传递空数组避免重复下载
            []
        )
        
        logger.success(f"VentureBeat文章抓取成功: {article_data.title}")
        
        return FetchResponse(
            success=True,
            message="VentureBeat文章抓取成功",
            data=saved_metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"抓取VentureBeat文章失败: {e}")
        raise HTTPException(status_code=500, detail=f"抓取失败: {str(e)}")

@router.post("/fetch-url", response_model=FetchResponse)
async def fetch_url(request: FetchRequest):
    """抓取指定URL的内容"""
    try:
        html, title = await CrawlerService.get_page_content(str(request.url))
        content_data = CrawlerService.extract_content(html, str(request.url))
        metadata = CrawlerService.save_results(
            str(request.url), 
            title, 
            content_data['content'], 
            content_data['images'],
            content_data.get('videos', [])  # 传递视频数据
        )
        
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

        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        client = OpenAI(api_key=api_key, base_url=base_url)

        vmin = request.voiceover_min_chars
        vmax = request.voiceover_max_chars
        from utils.content_methodology import build_methodology_prompt_section

        json_template = f"""
【输出 JSON 格式】（严格遵守，不要返回其他内容）
{{
  "target_audience": "推断的目标受众（≤12个汉字）",
  "praise_tags": ["夸赞标签1", "夸赞标签2", "夸赞标签3"],
  "traffic_hook": "流量钩子类型中文名（如「观众想看结果」），可空字符串",
  "main_line1": "主标题第一行（9~12汉字当量，话题引入，不含emoji）",
  "main_line2": "主标题第二行（9~12汉字当量，核心夸赞，可空字符串）",
  "sub_title": "副标题第一行（11~15汉字当量，轻观点收尾，不含emoji）",
  "sub_title2": "副标题第二行（11~15汉字当量，七种流量钩子之一，可空字符串）",
  "summary": "生成的摘要（40-50字，以「小牛说：」开头）",
  "tags": "#赛道标签 #垂直标签 #精准标签 #热点标签 #小牛说 #其他标签1 #其他标签2 #其他标签3 #其他标签4 #其他标签5",
  "voiceover_script": "口播稿全文（{vmin}~{vmax}字，以「小牛说：」开头）",
  "highlight_keywords": ["摘要中连续子串1", "子串2", "子串3"]
}}

【输入】
原标题：{request.title}

正文：
{request.content[:3000]}
"""
        prompt = build_methodology_prompt_section(
            vmin=vmin, vmax=vmax, json_template=json_template
        )

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {"role": "system", "content": "你是顶级自媒体爆款文案大师，精通微信视频号的「社交货币 / 夸赞」方法论：通过高情商夸赞目标受众、帮用户立人设来触发社交裂变点赞；同时熟练掌握「制造悬念、列举数字、提出疑问、强调时效、引发争议（中立可讨论）、指向明确」六种辅助标题技法，能在方法论为主、技法为辅的前提下综合运用。你的文案在合规前提下引发点赞与传播，信息密度高。绝对不使用任何emoji表情符号。请严格按照JSON格式返回结果。"
                + "我是小牛，一个专业的AI技术专家，对AI行业有深度的见解，请你根据正文为我生成标题、副标题、摘要、标签与口播稿。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192")),
            response_format={"type": "json_object"}
        )

        result_text = (response.choices[0].message.content or "").strip()
        if not result_text:
            finish = response.choices[0].finish_reason if response.choices else None
            usage = getattr(response, "usage", None)
            logger.error(
                f"LLM 返回空内容 | model={model} base_url={base_url} "
                f"finish_reason={finish} usage={usage}"
            )
            return {
                "success": False,
                "message": (
                    f"LLM 返回空内容（model={model}）。可能原因：1) 模型名拼错或不存在；"
                    "2) endpoint 不支持该模型；3) response_format=json_object 不被该模型支持；"
                    "4) 余额/鉴权问题。请检查 .env 的 DEEPSEEK_MODEL / DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY。"
                ),
            }
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError as e:
            logger.error(
                f"LLM 返回非 JSON | model={model} error={e} "
                f"head={result_text[:200]!r}"
            )
            return {
                "success": False,
                "message": (
                    f"LLM 返回非 JSON（model={model}，{e.msg}）。"
                    "可能该模型不支持 response_format=json_object，或 prompt 被截断。"
                    "返回内容前 200 字符已记录到日志。"
                ),
            }

        tags = normalize_structured_tags(result.get('tags', ''))
        main_line1 = ((result.get('main_line1') or result.get('main_title') or result.get('title', '')) or '').strip()
        main_line2 = (result.get('main_line2') or '').strip()
        sub_title = (result.get('sub_title') or '').strip()
        sub_title2 = (result.get('sub_title2') or '').strip()
        traffic_hook = (result.get('traffic_hook') or '').strip()
        # 兼容旧字段：main_title 为第一行，title 仍给前端作 legacy 拼接
        combined_title = "|".join([x for x in [main_line1, main_line2, sub_title, sub_title2] if x])
        summary_text = result.get("summary") or ""
        voiceover_script = (result.get("voiceover_script") or "").strip()
        from utils.summary_highlights import normalize_highlight_keywords_from_llm

        highlight_keywords = normalize_highlight_keywords_from_llm(
            result.get("highlight_keywords"), summary_text
        )
        # 社交货币方法论：LLM 推断回显
        target_audience = (result.get("target_audience") or "").strip()
        raw_praise_tags = result.get("praise_tags") or []
        if isinstance(raw_praise_tags, str):
            raw_praise_tags = [t.strip() for t in raw_praise_tags.replace("，", ",").split(",") if t.strip()]
        praise_tags = [str(t).strip() for t in raw_praise_tags if str(t).strip()][:5]
        logger.success(
            f"标题生成成功 - 受众:{target_audience}, 夸赞:{praise_tags}, 钩子:{traffic_hook}, "
            f"L1:{main_line1}, L2:{main_line2}, 副1:{sub_title}, 副2:{sub_title2}, "
            f"摘要:{len(summary_text)}字, 口播:{len(voiceover_script)}字"
        )

        return {
            "success": True,
            "title": combined_title,
            "main_line1": main_line1,
            "main_line2": main_line2,
            "main_title": main_line1,
            "sub_title": sub_title,
            "sub_title2": sub_title2,
            "summary": summary_text,
            "voiceover_script": voiceover_script,
            "tags": tags,
            "highlight_keywords": highlight_keywords,
            "target_audience": target_audience,
            "praise_tags": praise_tags,
            "traffic_hook": traffic_hook,
            "tokens_used": response.usage.total_tokens,
            "model": model
        }
    except Exception as e:
        logger.error(f"生成摘要失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成摘要失败: {str(e)}")

@router.post("/generate-image")
async def generate_image(request: GenerateImageRequest):
    """生成视频关键帧"""
    try:
        from ...services.video_service import VideoService
        result = await asyncio.to_thread(
            VideoService.create_video_frames,
            request.title,
            request.summary,
            request.images,
            main_line1=request.main_line1 or "",
            main_line2=request.main_line2 or "",
            subtitle=request.subtitle or "",
            subtitle2=request.subtitle2 or "",
            title_font_key=request.title_font_key,
            title_font_size=request.title_font_size,
            title_y_percent=request.title_y_percent,
            summary_y_percent=request.summary_y_percent,
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