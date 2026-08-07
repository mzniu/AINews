"""LLM commentary and grade adjustment for article scoring (flash-news profile)."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from services.ingestion.article_scorer import ArticleScoreResult, VALID_GRADES


def _build_client() -> OpenAI | None:
    from services.model_config.registry import get_language_client

    client, _profile = get_language_client()
    if client is not None:
        return client

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key_here":
        return None
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return OpenAI(api_key=api_key, base_url=base_url)


def _resolve_language_model() -> str:
    from services.model_config.registry import get_active_language_profile

    profile = get_active_language_profile()
    if profile and profile.get("model"):
        return str(profile["model"])
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def generate_score_review(
    *,
    title: str,
    summary: str | None,
    source_id: str,
    rule_result: ArticleScoreResult,
    content_excerpt: str | None = None,
) -> dict[str, Any] | None:
    """Return LLM JSON with commentary and optional grade adjustment."""
    client = _build_client()
    if client is None:
        return None

    model = _resolve_language_model()
    breakdown = rule_result.to_dict()
    prompt = f"""你是 AI 快讯频道的选题主编。规则引擎已给出初评，请你复核并可在必要时修正级别（快讯视角：时效>深度）。

【文章】
来源：{source_id}
标题：{title}
摘要：{summary or "无"}
正文节选：{(content_excerpt or "")[:1200]}

【规则初评】
总分：{breakdown["total"]}（{breakdown["grade"]}级）
建议：{breakdown["recommendation"]}
维度：{json.dumps(breakdown["dimensions"], ensure_ascii=False)}
加减分：加分={breakdown["bonuses"]} 扣分={breakdown["penalties"]}

【修正原则】
- 规则分偏高：旧闻翻炒、标题党、无实质信息、纯营销 → 可下调 1-2 级
- 规则分偏低：突发重磅、名企名人、强传播钩子被漏判 → 可上调
- 快讯频道：24h 内突发优先；超过 3 天且非里程碑事件应降级
- adjusted_grade 必须是 S/A/B/C/D 之一；adjusted_score 为 0-100 整数

请输出 JSON（不要其它内容）：
{{
  "flash_verdict": "一句话快讯价值判断（≤30字）",
  "headline_angle": "建议快讯标题切入角度（≤40字）",
  "why_now": "为什么现在值得/不值得发（≤50字）",
  "risks": "快讯风险或注意点（可空，≤40字）",
  "comment": "综合评语（80-120字，口语化，给运营看）",
  "adjusted_grade": "S或A或B或C或D（修正后等级，可与初评相同）",
  "adjusted_score": 0,
  "grade_adjust_reason": "若调整等级，说明原因；未调整则写「维持规则评级」"
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是资深 AI 自媒体快讯编辑，输出简洁、可执行的 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            return None
        payload = json.loads(raw)
        return _normalize_llm_payload(payload)
    except (json.JSONDecodeError, Exception):
        return None


def _normalize_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    grade = str(payload.get("adjusted_grade") or "").strip().upper()
    if grade not in VALID_GRADES:
        payload.pop("adjusted_grade", None)
    else:
        payload["adjusted_grade"] = grade

    score_raw = payload.get("adjusted_score")
    if score_raw is not None:
        try:
            payload["adjusted_score"] = max(0, min(100, int(float(score_raw))))
        except (TypeError, ValueError):
            payload.pop("adjusted_score", None)

    return payload


# Backward-compatible alias
def generate_score_commentary(**kwargs: Any) -> dict[str, Any] | None:
    return generate_score_review(**kwargs)
