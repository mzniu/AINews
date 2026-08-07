"""AI 生成内容的合规校验与 LLM 重试辅助。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from utils.forbidden_words import (
    CONTENT_FIELD_NAMES,
    ForbiddenWordsRegistry,
    Violation,
    get_registry,
    partition_violations,
    scan_content_fields,
)


@dataclass
class ComplianceResult:
    ok: bool
    violations: List[Violation]
    retried: bool = False
    tokens_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return build_compliance_payload(self.ok, self.violations, retried=self.retried)


def extract_fields_from_llm_result(result: Dict[str, Any]) -> Dict[str, Any]:
    main_line1 = (
        (result.get("main_line1") or result.get("main_title") or result.get("title", "")) or ""
    ).strip()
    main_line2 = (result.get("main_line2") or "").strip()
    sub_title = (result.get("sub_title") or "").strip()
    sub_title2 = (result.get("sub_title2") or "").strip()
    summary = (result.get("summary") or "").strip()
    voiceover_script = (result.get("voiceover_script") or "").strip()
    tags = result.get("tags", "")
    if isinstance(tags, list):
        tags = " ".join(str(item) for item in tags)
    tags = str(tags or "").strip()
    target_audience = (result.get("target_audience") or "").strip()

    praise_tags = result.get("praise_tags") or []
    if isinstance(praise_tags, str):
        praise_tags = [item.strip() for item in praise_tags.replace("，", ",").split(",") if item.strip()]
    praise_tags = [str(item).strip() for item in praise_tags if str(item).strip()]

    highlight_keywords = result.get("highlight_keywords") or []
    if isinstance(highlight_keywords, str):
        highlight_keywords = [item.strip() for item in highlight_keywords.replace("，", ",").split(",") if item.strip()]
    highlight_keywords = [str(item).strip() for item in highlight_keywords if str(item).strip()]

    return {
        "main_line1": main_line1,
        "main_line2": main_line2,
        "sub_title": sub_title,
        "sub_title2": sub_title2,
        "summary": summary,
        "voiceover_script": voiceover_script,
        "tags": tags,
        "highlight_keywords": highlight_keywords,
        "praise_tags": praise_tags,
        "target_audience": target_audience,
    }


def validate_llm_result(
    result: Dict[str, Any],
    *,
    registry: Optional[ForbiddenWordsRegistry] = None,
) -> ComplianceResult:
    active = registry or get_registry()
    violations = scan_content_fields(extract_fields_from_llm_result(result), registry=active)
    errors, _warnings = partition_violations(violations)
    return ComplianceResult(ok=not errors, violations=violations)


def build_compliance_payload(
    ok: bool,
    violations: Sequence[Violation],
    *,
    retried: bool = False,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "retried": retried,
        "violations": [item.to_dict() for item in violations],
    }


def build_retry_user_message(violations: Sequence[Violation]) -> str:
    errors, warnings = partition_violations(violations)
    focus = errors or list(warnings)
    if not focus:
        return ""
    lines = [
        "【合规改写要求】你上一次输出命中禁限词，请在不改变事实的前提下全部改写，并重新输出完整 JSON。",
        "命中明细：",
    ]
    for item in focus:
        lines.append(
            f"- 字段 {item.field} 命中「{item.matched}」（分类：{item.category_name}）"
        )
    lines.append("请逐字段自检，确保不再出现上述禁限词及同义变体。")
    return "\n".join(lines)


def invoke_json_llm_with_compliance(
    *,
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict[str, str]] = None,
    registry: Optional[ForbiddenWordsRegistry] = None,
) -> tuple[Dict[str, Any], ComplianceResult]:
    """调用 LLM 生成 JSON，并按配置执行违禁词后检与一次重试。"""
    active = registry or get_registry()
    create_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        create_kwargs["response_format"] = response_format

    response = client.chat.completions.create(**create_kwargs)
    result_text = (response.choices[0].message.content or "").strip()
    tokens_used = _extract_tokens(response)
    if not result_text:
        raise ValueError("LLM 返回空内容")

    result = json.loads(result_text)
    compliance = validate_llm_result(result, registry=active)
    compliance.tokens_used = tokens_used
    if (
        active.settings.post_check
        and not compliance.ok
        and active.settings.on_violation == "retry_once"
        and active.settings.max_retry > 0
    ):
        retry_messages = list(messages)
        retry_messages.append({"role": "assistant", "content": result_text})
        retry_messages.append(
            {"role": "user", "content": build_retry_user_message(compliance.violations)}
        )
        retry_response = client.chat.completions.create(
            model=model,
            messages=retry_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **({"response_format": response_format} if response_format else {}),
        )
        retry_text = (retry_response.choices[0].message.content or "").strip()
        tokens_used += _extract_tokens(retry_response)
        if retry_text:
            result = json.loads(retry_text)
            compliance = validate_llm_result(result, registry=active)
            compliance.retried = True
            compliance.tokens_used = tokens_used
    return result, compliance


def _extract_tokens(response: Any) -> int:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    total = getattr(usage, "total_tokens", None)
    return int(total or 0)


def scan_plain_text(
    text: str,
    *,
    field: str = "summary",
    registry: Optional[ForbiddenWordsRegistry] = None,
) -> List[Violation]:
    active = registry or get_registry()
    return active.scan_text(text, field=field)
