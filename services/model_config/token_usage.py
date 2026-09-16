"""Record and query LLM/VL token usage from chat completion responses."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.db.models.llm_usage import LlmTokenUsageEvent
from src.utils.beijing_time import beijing_now

USAGE_TASK_LABELS = {
    "article_score": "文章评分",
    "story_cluster": "故事聚类",
    "image_score": "配图评分",
    "content_gen": "成片文案",
    "highlights": "摘要高亮",
    "related_image_query": "相关配图",
    "model_test": "模型测试",
    "crawler_content": "爬虫文案",
    "comment_reply": "评论回复",
}

_VALID_RANGES = frozenset({"today", "7d", "30d", "all"})


def env_language_profile(model: str | None = None) -> dict[str, Any]:
    resolved = str(model or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()
    return {
        "id": "env_deepseek",
        "provider": "deepseek",
        "model": resolved,
        "display_name": "DeepSeek（.env）",
    }


def resolve_language_profile(model: str | None = None) -> dict[str, Any]:
    from services.model_config.registry import get_language_client

    _client, profile = get_language_client()
    if profile:
        return profile
    return env_language_profile(model)


def parse_completion_usage(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0, 0
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total_raw = getattr(usage, "total_tokens", None)
    total = int(total_raw) if total_raw is not None else prompt + completion
    return prompt, completion, total


def record_token_usage(
    *,
    kind: str,
    profile_id: str | None,
    provider: str,
    model: str,
    task: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    session: Session | None = None,
) -> None:
    event = LlmTokenUsageEvent(
        kind=kind,
        profile_id=profile_id,
        provider=provider or "",
        model=model or "",
        task=task or "",
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        total_tokens=int(total_tokens or 0),
    )
    if session is not None:
        session.add(event)
        return
    try:
        from services.ingestion.db_retry import serialized_sqlite_write
        from src.db.engine import session_scope

        def _write() -> None:
            with session_scope() as scoped:
                scoped.add(event)

        serialized_sqlite_write(_write)
    except Exception as exc:
        logger.warning("token usage record failed: {}", exc)


def _range_start_utc(range_key: str) -> datetime | None:
    key = (range_key or "").strip()
    if key not in _VALID_RANGES:
        raise ValueError(f"invalid range: {range_key}")
    if key == "all":
        return None
    now_bj = beijing_now()
    if key == "today":
        start_bj = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    elif key == "7d":
        start_bj = now_bj - timedelta(days=7)
    else:
        start_bj = now_bj - timedelta(days=30)
    return start_bj.astimezone(timezone.utc).replace(tzinfo=None)


def query_token_usage(session: Session, *, range_key: str) -> dict[str, Any]:
    start = _range_start_utc(range_key)
    query = session.query(LlmTokenUsageEvent)
    if start is not None:
        query = query.filter(LlmTokenUsageEvent.created_at >= start)
    events = query.all()

    totals = {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "language_tokens": 0,
        "vision_tokens": 0,
    }
    model_acc: dict[tuple, dict[str, Any]] = {}
    task_acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )

    for event in events:
        totals["calls"] += 1
        totals["prompt_tokens"] += event.prompt_tokens
        totals["completion_tokens"] += event.completion_tokens
        totals["total_tokens"] += event.total_tokens
        if event.kind == "language":
            totals["language_tokens"] += event.total_tokens
        elif event.kind == "vision":
            totals["vision_tokens"] += event.total_tokens

        model_key = (event.kind, event.profile_id, event.provider, event.model)
        row = model_acc.setdefault(
            model_key,
            {
                "kind": event.kind,
                "profile_id": event.profile_id,
                "provider": event.provider,
                "model": event.model,
                "display_name": event.model,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
        row["calls"] += 1
        row["prompt_tokens"] += event.prompt_tokens
        row["completion_tokens"] += event.completion_tokens
        row["total_tokens"] += event.total_tokens

        task_row = task_acc[event.task]
        task_row["calls"] += 1
        task_row["prompt_tokens"] += event.prompt_tokens
        task_row["completion_tokens"] += event.completion_tokens
        task_row["total_tokens"] += event.total_tokens

    by_model = sorted(model_acc.values(), key=lambda item: (-item["total_tokens"], item["model"]))
    by_task = [
        {
            "task": task,
            "label": USAGE_TASK_LABELS.get(task, task),
            **values,
        }
        for task, values in sorted(task_acc.items(), key=lambda item: (-item[1]["total_tokens"], item[0]))
    ]
    return {"totals": totals, "by_model": by_model, "by_task": by_task}


def clear_token_usage(session: Session) -> int:
    deleted = session.query(LlmTokenUsageEvent).delete()
    return int(deleted or 0)


def complete_chat(
    client: Any,
    *,
    kind: str,
    profile: dict[str, Any] | None,
    task: str,
    **kwargs: Any,
) -> Any:
    response = client.chat.completions.create(**kwargs)
    prompt, completion, total = parse_completion_usage(response)
    profile = profile or {}
    try:
        record_token_usage(
            kind=kind,
            profile_id=str(profile.get("id") or "") or None,
            provider=str(profile.get("provider") or ""),
            model=str(kwargs.get("model") or profile.get("model") or ""),
            task=task,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
        )
    except Exception as exc:
        logger.warning("token usage record failed after completion: {}", exc)
    return response
