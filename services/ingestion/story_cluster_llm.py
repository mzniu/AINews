"""LLM adjudication for gray-zone story clustering."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from src.db.models.ingestion import IngestedArticle


def build_language_client() -> OpenAI | None:
    from services.model_config.registry import get_language_client

    client, _profile = get_language_client()
    if client is not None:
        return client

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key_here":
        return None
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return OpenAI(api_key=api_key, base_url=base_url)


def _language_profile() -> dict[str, Any]:
    from services.model_config.token_usage import resolve_language_profile

    return resolve_language_profile()


def resolve_language_model() -> str:
    from services.model_config.registry import get_active_language_profile

    profile = get_active_language_profile()
    if profile and profile.get("model"):
        return str(profile["model"])
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def _article_brief(article: IngestedArticle) -> dict[str, str]:
    return {
        "id": article.id,
        "source_id": article.source_id or "",
        "title": article.title or "",
        "summary": (article.summary or "")[:400],
        "excerpt": (article.content_text or "")[:500],
    }


def adjudicate_same_story(
    left: IngestedArticle,
    right: IngestedArticle,
    *,
    rule_score: float,
    blended_score: float,
) -> dict[str, Any] | None:
    """Return {same_story, confidence, reason} or None when LLM unavailable."""
    client = build_language_client()
    if client is None:
        return None

    model = resolve_language_model()
    payload = {
        "article_a": _article_brief(left),
        "article_b": _article_brief(right),
        "rule_score": round(rule_score, 3),
        "blended_score": round(blended_score, 3),
    }
    prompt = f"""你是新闻去重编辑。判断以下两篇文章是否报道【同一新闻事件/同一话题】（允许不同来源、不同标题写法）。

注意：
- 同一公司但不同事件（如「发布产品」vs「裁员」）→ 不同题
- 同一事件的不同角度跟进 → 同题
- 旧闻翻炒若核心事件相同 → 同题

输入：
{json.dumps(payload, ensure_ascii=False)}

输出 JSON（不要其它内容）：
{{
  "same_story": true,
  "confidence": 0.0,
  "reason": "≤60字说明"
}}"""

    try:
        from services.model_config.token_usage import complete_chat

        response = complete_chat(
            client,
            kind="language",
            profile=_language_profile(),
            task="story_cluster",
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是严谨的中文科技新闻编辑，只输出 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            return None
        data = json.loads(raw)
        return {
            "same_story": bool(data.get("same_story")),
            "confidence": max(0.0, min(1.0, float(data.get("confidence", 0)))),
            "reason": str(data.get("reason") or "").strip(),
        }
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return None


def review_story_members(
    *,
    story_title: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Review whether story members are coherent; suggest outliers to split."""
    client = build_language_client()
    if client is None:
        return None

    model = resolve_language_model()
    prompt = f"""你是新闻聚类质检编辑。以下是一个「同题 Story」内的文章列表，请判断聚类是否合理。

Story 标题：{story_title}
成员：
{json.dumps(articles, ensure_ascii=False)}

输出 JSON：
{{
  "coherent": true,
  "confidence": 0.0,
  "summary": "≤50字总体判断",
  "outlier_article_ids": [],
  "reason": "≤120字说明"
}}"""

    try:
        from services.model_config.token_usage import complete_chat

        response = complete_chat(
            client,
            kind="language",
            profile=_language_profile(),
            task="story_cluster",
            model=model,
            messages=[
                {"role": "system", "content": "你是严谨的中文科技新闻编辑，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            return None
        data = json.loads(raw)
        outliers = data.get("outlier_article_ids") or []
        if not isinstance(outliers, list):
            outliers = []
        return {
            "coherent": bool(data.get("coherent", True)),
            "confidence": max(0.0, min(1.0, float(data.get("confidence", 0)))),
            "summary": str(data.get("summary") or "").strip(),
            "outlier_article_ids": [str(item) for item in outliers],
            "reason": str(data.get("reason") or "").strip(),
        }
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return None


def review_merge_stories(
    *,
    story_a: dict[str, Any],
    story_b: dict[str, Any],
    blended_score: float,
) -> dict[str, Any] | None:
    """Whether two stories should be merged."""
    client = build_language_client()
    if client is None:
        return None

    model = resolve_language_model()
    prompt = f"""判断以下两个 Story 是否应合并为同一话题（同一新闻事件）。

Story A：
{json.dumps(story_a, ensure_ascii=False)}

Story B：
{json.dumps(story_b, ensure_ascii=False)}

规则相似度：{round(blended_score, 3)}

输出 JSON：
{{
  "should_merge": false,
  "confidence": 0.0,
  "reason": "≤80字说明"
}}"""

    try:
        from services.model_config.token_usage import complete_chat

        response = complete_chat(
            client,
            kind="language",
            profile=_language_profile(),
            task="story_cluster",
            model=model,
            messages=[
                {"role": "system", "content": "你是严谨的中文科技新闻编辑，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=350,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            return None
        data = json.loads(raw)
        return {
            "should_merge": bool(data.get("should_merge")),
            "confidence": max(0.0, min(1.0, float(data.get("confidence", 0)))),
            "reason": str(data.get("reason") or "").strip(),
        }
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return None
