"""Shared LLM content generation for video titles, summaries, and voiceover scripts."""
from __future__ import annotations

import json
import os
from typing import Any

from loguru import logger
from openai import OpenAI

from utils.content_compliance import invoke_json_llm_with_compliance
from utils.content_methodology import build_methodology_prompt_section
from utils.summary_highlights import normalize_highlight_keywords_from_llm
from utils.tags_normalizer import normalize_structured_tags

_SYSTEM_PROMPT = (
    "你是顶级自媒体爆款文案大师，精通微信视频号的「社交货币 / 夸赞」方法论：通过高情商夸赞目标受众、"
    "帮用户立人设来触发社交裂变点赞；同时熟练掌握「制造悬念、列举数字、提出疑问、强调时效、引发争议"
    "（中立可讨论）、指向明确」六种辅助标题技法，能在方法论为主、技法为辅的前提下综合运用。"
    "主标题第一行必须以贴合正文的感叹词（如突发！、炸裂！、爽了！等）开头抓眼球。"
    "你的文案在合规前提下引发点赞与传播，信息密度高。绝对不使用任何emoji表情符号。"
    "请严格按照JSON格式返回结果。"
    "我是小牛，一个专业的AI技术专家，对AI行业有深度的见解，请你根据正文为我生成标题、副标题、摘要、标签与口播稿。"
)


def _build_openai_client() -> tuple[OpenAI, str, str]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key_here":
        raise RuntimeError("请在.env文件中配置DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    return OpenAI(api_key=api_key, base_url=base_url), model, base_url


def generate_video_content(
    *,
    title: str,
    content: str,
    voiceover_min_chars: int = 40,
    voiceover_max_chars: int = 90,
    content_max_chars: int = 3000,
) -> dict[str, Any]:
    """Generate homepage-compatible video copy (sync). Returns success payload or raises."""
    client, model, _base_url = _build_openai_client()
    vmin = max(20, int(voiceover_min_chars))
    vmax = max(vmin, int(voiceover_max_chars))

    json_template = f"""
【输出 JSON 格式】（严格遵守，不要返回其他内容）
{{
  "target_audience": "推断的目标受众（≤12个汉字）",
  "praise_tags": ["夸赞标签1", "夸赞标签2", "夸赞标签3"],
  "traffic_hook": "流量钩子类型中文名（如「观众想看结果」），可空字符串",
  "main_line1": "主标题第一行（9~12汉字当量，必须以感叹词如突发！/炸裂！/爽了！等开头+话题引入，不含emoji）",
  "main_line2": "主标题第二行（9~12汉字当量，必须以「网友：」开头的尖锐锐评，可空字符串）",
  "sub_title": "副标题第一行（11~15汉字当量，轻观点收尾，不含emoji）",
  "sub_title2": "副标题第二行（11~15汉字当量，七种流量钩子之一，可空字符串）",
  "summary": "生成的摘要（40-50字，以「小牛说：」开头）",
  "tags": "#赛道标签 #垂直标签 #精准标签 #热点标签 #小牛说 #其他标签1 #其他标签2 #其他标签3 #其他标签4 #其他标签5",
  "voiceover_script": "口播稿全文（{vmin}~{vmax}字，以「小牛说：」开头，适合8-12秒短视频）",
  "highlight_keywords": ["摘要中连续子串1", "子串2", "子串3"]
}}

【输入】
原标题：{title}

正文：
{(content or "")[:content_max_chars]}
"""
    prompt = build_methodology_prompt_section(vmin=vmin, vmax=vmax, json_template=json_template)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    result, compliance = invoke_json_llm_with_compliance(
        client=client,
        model=model,
        messages=messages,
        temperature=0.85,
        max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192")),
        response_format={"type": "json_object"},
    )

    tags = normalize_structured_tags(result.get("tags", ""))
    main_line1 = ((result.get("main_line1") or result.get("main_title") or result.get("title", "")) or "").strip()
    main_line2 = (result.get("main_line2") or "").strip()
    sub_title = (result.get("sub_title") or "").strip()
    sub_title2 = (result.get("sub_title2") or "").strip()
    traffic_hook = (result.get("traffic_hook") or "").strip()
    combined_title = "|".join([x for x in [main_line1, main_line2, sub_title, sub_title2] if x])
    summary_text = result.get("summary") or ""
    voiceover_script = (result.get("voiceover_script") or "").strip()
    highlight_keywords = normalize_highlight_keywords_from_llm(
        result.get("highlight_keywords"), summary_text
    )
    target_audience = (result.get("target_audience") or "").strip()
    raw_praise_tags = result.get("praise_tags") or []
    if isinstance(raw_praise_tags, str):
        raw_praise_tags = [t.strip() for t in raw_praise_tags.replace("，", ",").split(",") if t.strip()]
    praise_tags = [str(t).strip() for t in raw_praise_tags if str(t).strip()][:5]

    logger.success(
        f"视频文案生成成功 - 受众:{target_audience}, L1:{main_line1}, 摘要:{len(summary_text)}字, 口播:{len(voiceover_script)}字"
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
        "tokens_used": compliance.tokens_used,
        "model": model,
        "compliance": compliance.to_dict(),
    }
