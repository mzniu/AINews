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
import re
from openai import OpenAI

router = APIRouter(prefix="/api", tags=["爬虫"])

DEFAULT_STRUCTURED_TAGS = [
    '#人工智能', '#AI应用', '#AI资讯', '#AIAgent', '#小牛说',
    '#科技前沿', '#大模型', '#效率工具', '#行业观察', '#技术趋势'
]


def normalize_structured_tags(tags_value) -> str:
    """将模型标签结果整理为固定 10 个结构化标签。"""
    if isinstance(tags_value, list):
        raw_text = ' '.join(str(tag) for tag in tags_value)
    else:
        raw_text = str(tags_value or '')

    hashtag_matches = re.findall(r"#[^\s,，、；;。.]+", raw_text)
    raw = raw_text.replace('，', ' ').replace(',', ' ').replace('、', ' ')
    parts = hashtag_matches or re.split(r"\s+", raw.strip())

    tags = []
    seen = set()
    for part in parts:
        tag = part.strip().strip('；;。.')
        if not tag:
            continue
        if not tag.startswith('#'):
            tag = f"#{tag.lstrip('#')}"
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    for tag in DEFAULT_STRUCTURED_TAGS:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    has_ip_tag = '#小牛说' in tags or '#小牛说AI' in tags
    if not has_ip_tag:
        tags.insert(4, '#小牛说')
    elif len(tags) >= 5 and tags[4] not in ('#小牛说', '#小牛说AI'):
        ip_tag = '#小牛说' if '#小牛说' in tags else '#小牛说AI'
        tags = [tag for tag in tags if tag != ip_tag]
        tags.insert(4, ip_tag)

    deduped = []
    seen.clear()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
        if len(deduped) == 10:
            break
    return ' '.join(deduped)


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
        
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        vmin = request.voiceover_min_chars
        vmax = request.voiceover_max_chars
        prompt = f"""请为以下文章生成适合微信视频号等短视频平台的标题、摘要、标签、口播稿。

【短视频标题六大实用技法】请在全文案中综合运用，主标题/副标题至少体现其中 2～3 种；摘要与口播可自然穿插，勿生硬堆砌：
1）制造悬念：只露一部分信息，关键结论留到正文/视频里，激发「想看下去」。
2）列举数字：用具体数字（时长、数量、比例、版本号等）增强冲击力与可感知承诺。
3）提出疑问：直击目标读者心里会问的问题，引出答案。
4）强调时效：突出新规、更新、窗口期、截止日期等，营造「现在就要看」的紧迫感（须基于原文事实，不编造日期）。
5）引发争议：可选用有讨论空间的中立话题引发评论（不煽动对立、不人身攻击）。
6）指向明确：直接点出「谁该看」——新手、从业者、某类痛点人群等，让读者快速对号入座。

【分项要求】
1. 主标题第一行：「14～18个汉字当量」。计法：每个汉字计1；每个英文字母或数字计0.5。优先融合技法 1/2/3/6；点明核心看点，不使用任何emoji表情。
2. 主标题第二行：「16～20个汉字当量」（英文数字计0.5），与第一行形成钩子+信息补全；可衔接技法 2/4/6；不需要时可填空字符串 ""。
3. 副标题：单独一行，「14～16个汉字当量」（英文数字计0.5），侧重技法 1（悬念补充）、4（时效）、5（适度可讨论）或 6（受众）；不使用任何emoji表情。
4. 摘要：40-50字，简洁有力，适合短视频口播解说，节奏感强。以“小牛说：”开头，客观、理性、中立的语气，带适度幽默感与专业感；可自然融入疑问、数字或受众指向；避免空洞情绪化表达；不使用任何emoji表情；结尾给出一个引人评论的观点或问题（若用技法5须保持中立）。
5. 标签：严格生成10个标签，每个标签以#开头，用空格分隔，顺序和类型必须固定为：第1个赛道标签（宏观领域/行业赛道，如 #人工智能、#开源项目、#机器人）；第2个垂直标签（细分方向/应用场景，如 #AI编程、#多模态、#智能体）；第3个精准标签（本文最核心对象、项目名、产品名、技术名或关键概念，如 #DeepSeek、#WorldMonitor、#端侧模型）；第4个热点标签（当前传播热点、趋势、事件或高关注话题，如 #AIAgent、#大模型应用、#GitHub热门）；第5个个人IP标签（固定围绕“小牛说”个人IP，优先使用 #小牛说，也可根据内容使用 #小牛说AI）；第6～10个为其他补充标签（技术栈、受众、价值点、平台、场景等），不要与前5个重复。
6. 口播稿（voiceover_script）：与摘要有区分，为完整配音用长稿，中文按字符计数，总长度必须严格在 {vmin}～{vmax} 字之间（含边界）。结构清晰、口语化、适合直接朗读与烧录字幕；以“小牛说：”开头；可分层展开：悬念引入→关键数字/事实→疑问回应→（可选）时效或受众收尾；客观理性带适度幽默；不使用任何emoji表情。
7. 摘要高亮（highlight_keywords）：JSON 数组，3～5 个字符串。每个必须是「摘要」原文中的连续子串（一字不差）。中文片段每个不超过 5 个字符；纯英文单词请整词输出（不要只输出前几个字母）。优先从第 5 步标签里去掉 # 后能在摘要中出现的词，再补足摘要内信息密度高的词。用于成片画面关键词着色。

原标题：{request.title}

正文：
{request.content[:3000]}

请按以下JSON格式返回：
{{
  "main_line1": "主标题第一行（14～18汉字当量，英文数字算0.5，不含emoji）",
  "main_line2": "主标题第二行（16～20汉字当量，可空字符串）",
  "sub_title": "副标题（14～16汉字当量，不含emoji）",
  "summary": "生成的摘要（40-50字）",
    "tags": "#赛道标签 #垂直标签 #精准标签 #热点标签 #小牛说 #其他标签1 #其他标签2 #其他标签3 #其他标签4 #其他标签5",
  "voiceover_script": "口播稿全文（{vmin}～{vmax}字）",
  "highlight_keywords": ["摘要中连续子串1", "子串2", "子串3"]
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是顶级自媒体爆款文案大师，精通微信视频号等平台的内容运营，熟练掌握「制造悬念、列举数字、提出疑问、强调时效、引发争议（中立可讨论）、指向明确」六种标题技法，并能将其迁移到副标题、短摘要与长口播的结构设计中。你的标题与文案在合规前提下引发点击与互动，信息密度高。绝对不使用任何emoji表情符号。请严格按照JSON格式返回结果。"
                + "我是小牛，一个专业的AI技术专家，对AI行业有深度的见解，请你根据正文为我生成标题、副标题、摘要、标签与口播稿。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=1300,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        
        from utils.title_units import (
            truncate_han_equiv,
            MAIN_LINE1_MAX_UNITS,
            MAIN_LINE2_MAX_UNITS,
            SUBTITLE_MAX_UNITS,
        )

        tags = normalize_structured_tags(result.get('tags', ''))
        main_line1 = (result.get('main_line1') or result.get('main_title') or result.get('title', '')) or ''
        main_line2 = (result.get('main_line2') or '') or ''
        sub_title = (result.get('sub_title') or '') or ''
        main_line1 = truncate_han_equiv(main_line1.strip(), MAIN_LINE1_MAX_UNITS)
        main_line2 = truncate_han_equiv(main_line2.strip(), MAIN_LINE2_MAX_UNITS)
        sub_title = truncate_han_equiv(sub_title.strip(), SUBTITLE_MAX_UNITS)
        # 兼容旧字段：main_title 为第一行，title 仍给前端作 legacy 拼接
        combined_title = "|".join([x for x in [main_line1, main_line2, sub_title] if x])
        summary_text = result.get("summary") or ""
        voiceover_script = (result.get("voiceover_script") or "").strip()
        from utils.summary_highlights import normalize_highlight_keywords_from_llm

        highlight_keywords = normalize_highlight_keywords_from_llm(
            result.get("highlight_keywords"), summary_text
        )
        logger.success(
            f"标题生成成功 - L1:{main_line1}, L2:{main_line2}, 副:{sub_title}, 摘要:{len(summary_text)}字, 口播:{len(voiceover_script)}字"
        )

        return {
            "success": True,
            "title": combined_title,
            "main_line1": main_line1,
            "main_line2": main_line2,
            "main_title": main_line1,
            "sub_title": sub_title,
            "summary": summary_text,
            "voiceover_script": voiceover_script,
            "tags": tags,
            "highlight_keywords": highlight_keywords,
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
            request.images,
            main_line1=request.main_line1 or "",
            main_line2=request.main_line2 or "",
            subtitle=request.subtitle or "",
            title_font_key=request.title_font_key,
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