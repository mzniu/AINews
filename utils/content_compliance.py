"""AI 生成内容的合规校验与 LLM 重试辅助。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from loguru import logger

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
    short_title = (result.get("short_title") or "").strip()
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
        "short_title": short_title,
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


EMPTY_CONTENT_MAX_ATTEMPTS = 3
MAX_TOKENS_CAP = 32768


def _message_content(message: Any) -> str:
    return (getattr(message, "content", None) or "").strip()


def _finish_reason(choice: Any) -> str:
    return str(getattr(choice, "finish_reason", None) or "")


def _reasoning_content(message: Any) -> str:
    value = getattr(message, "reasoning_content", None)
    return value if isinstance(value, str) else ""


def _assistant_history_message(message: Any, content: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"role": "assistant", "content": content}
    reasoning = _reasoning_content(message)
    if reasoning:
        payload["reasoning_content"] = reasoning
    return payload


def _complete_json_text(
    *,
    client: Any,
    create_kwargs: Dict[str, Any],
    model: str,
    kind: str = "language",
    profile: Optional[Dict[str, Any]] = None,
    task: str = "content_gen",
) -> tuple[Any, str, int]:
    """Call chat.completions.create; retry empty content (common on thinking models)."""
    from services.model_config.token_usage import complete_chat, resolve_language_profile

    tokens_used = 0
    response = None
    result_text = ""
    last_reason = ""
    last_reasoning_len = 0
    kwargs = dict(create_kwargs)
    usage_profile = profile or resolve_language_profile(model)
    for attempt in range(EMPTY_CONTENT_MAX_ATTEMPTS):
        response = complete_chat(
            client,
            kind=kind,
            profile=usage_profile,
            task=task,
            **kwargs,
        )
        choice = response.choices[0]
        result_text = _message_content(choice.message)
        tokens_used += _extract_tokens(response)
        last_reason = _finish_reason(choice)
        last_reasoning_len = len(_reasoning_content(choice.message))
        if result_text:
            return response, result_text, tokens_used
        logger.warning(
            "LLM empty content attempt={}/{} finish_reason={} reasoning_chars={} model={}",
            attempt + 1,
            EMPTY_CONTENT_MAX_ATTEMPTS,
            last_reason or "unknown",
            last_reasoning_len,
            model,
        )
        if last_reason == "length":
            current = int(kwargs.get("max_tokens") or 0)
            kwargs["max_tokens"] = min(max(current * 2, current + 4096), MAX_TOKENS_CAP)
    raise ValueError(
        f"LLM 返回空内容 (finish_reason={last_reason or 'unknown'}, "
        f"reasoning_chars={last_reasoning_len})"
    )


def invoke_json_llm_with_compliance(
    *,
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict[str, str]] = None,
    registry: Optional[ForbiddenWordsRegistry] = None,
    kind: str = "language",
    profile: Optional[Dict[str, Any]] = None,
    task: str = "content_gen",
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

    response, result_text, tokens_used = _complete_json_text(
        client=client,
        create_kwargs=create_kwargs,
        model=model,
        kind=kind,
        profile=profile,
        task=task,
    )

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
        retry_messages.append(_assistant_history_message(response.choices[0].message, result_text))
        retry_messages.append(
            {"role": "user", "content": build_retry_user_message(compliance.violations)}
        )
        retry_kwargs = dict(create_kwargs)
        retry_kwargs["messages"] = retry_messages
        _, retry_text, retry_tokens = _complete_json_text(
            client=client,
            create_kwargs=retry_kwargs,
            model=model,
            kind=kind,
            profile=profile,
            task=task,
        )
        tokens_used += retry_tokens
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
