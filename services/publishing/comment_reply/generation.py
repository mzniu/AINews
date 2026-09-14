"""LLM generation for audience comment replies."""
from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from services.content_prompts import get_system_role, load_merged_content_prompts
from utils.content_compliance import invoke_json_llm_with_compliance


def _build_openai_client() -> tuple[OpenAI, str, dict]:
    from services.model_config.registry import get_language_client
    from services.model_config.token_usage import env_language_profile

    client, profile = get_language_client()
    if client is not None and profile:
        return client, str(profile.get("model") or ""), profile

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key_here":
        raise RuntimeError("请在.env文件中配置DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    return OpenAI(api_key=api_key, base_url=base_url), model, env_language_profile(model)


def _reply_patterns() -> str:
    prompts = load_merged_content_prompts().get("title") or {}
    return str(prompts.get("comment_reply_patterns") or "").strip()


def generate_comment_reply(
    *,
    post_title: str,
    post_description: str | None,
    audience_comment: str,
    audience_name: str | None = None,
    min_length: int = 5,
    max_length: int = 100,
) -> str:
    client, model, profile = _build_openai_client()
    patterns = _reply_patterns()
    user = f"""
{patterns}

【视频标题】{post_title}
【视频描述】{(post_description or '')[:800]}
【观众昵称】{audience_name or '观众'}
【观众评论】{audience_comment}

请先判断留言是夸赞、提问、质疑还是反讽/阴阳怪气，再写回复。
回复用陈述句为主，不要以疑问句结尾，不要刻意引导对方继续回复。
请只返回 JSON：{{"reply": "回复正文"}}
回复长度 {min_length}~{max_length} 字（尽量靠近下限，简短自然）。
"""
    messages = [
        {"role": "system", "content": get_system_role()},
        {"role": "user", "content": user.strip()},
    ]
    result, _compliance = invoke_json_llm_with_compliance(
        client=client,
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=512,
        response_format={"type": "json_object"},
        profile=profile,
        task="comment_reply",
    )
    reply = str((result or {}).get("reply") or "").strip()
    if not reply:
        raise RuntimeError("LLM 未返回 reply 字段")
    if len(reply) < min_length:
        raise RuntimeError(f"回复过短（{len(reply)}字）")
    if len(reply) > max_length:
        reply = reply[:max_length].rstrip()
    return reply


def validate_reply_text(text: str, *, min_length: int, max_length: int) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) < min_length:
        raise ValueError(f"回复至少 {min_length} 字")
    if len(cleaned) > max_length:
        raise ValueError(f"回复不能超过 {max_length} 字")
    return cleaned
