"""Tests for JSON LLM invoke: empty-content retry and reasoning round-trip."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from utils.content_compliance import invoke_json_llm_with_compliance
from utils.forbidden_words import ForbiddenWordsRegistry, Settings


def _registry(*, post_check: bool = False) -> ForbiddenWordsRegistry:
    return ForbiddenWordsRegistry(
        settings=Settings(post_check=post_check, on_violation="retry_once", max_retry=1),
        policy=[],
        categories=[],
    )


def _response(
    content: str | None,
    *,
    finish_reason: str = "stop",
    reasoning_content: str | None = None,
    total_tokens: int = 10,
):
    message = SimpleNamespace(content=content, reasoning_content=reasoning_content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(total_tokens=total_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


_OK_JSON = json.dumps(
    {
        "main_line1": "突发！模型发布",
        "main_line2": "",
        "sub_title": "具体数字更有说服力",
        "sub_title2": "",
        "summary": "小牛说：模型发布了。",
        "voiceover_script": "小牛说：口播稿内容。",
        "tags": "#人工智能",
        "highlight_keywords": ["模型发布"],
        "praise_tags": ["懂行"],
        "target_audience": "从业者",
    },
    ensure_ascii=False,
)


def test_retries_empty_content_then_succeeds():
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response("", finish_reason="length", reasoning_content="think " * 200),
        _response(_OK_JSON),
    ]

    result, compliance = invoke_json_llm_with_compliance(
        client=client,
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.5,
        max_tokens=8192,
        registry=_registry(),
    )

    assert result["main_line1"].startswith("突发")
    assert client.chat.completions.create.call_count == 2
    second_kwargs = client.chat.completions.create.call_args_list[1].kwargs
    assert second_kwargs["max_tokens"] > 8192
    assert compliance.tokens_used == 20


def test_empty_content_exhausted_includes_finish_reason():
    client = MagicMock()
    client.chat.completions.create.return_value = _response(
        None, finish_reason="length", reasoning_content="x" * 50
    )

    with pytest.raises(ValueError, match="LLM 返回空内容") as exc:
        invoke_json_llm_with_compliance(
            client=client,
            model="deepseek-v4-pro",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=8192,
            registry=_registry(),
        )

    assert "finish_reason=length" in str(exc.value)
    assert "reasoning_chars=50" in str(exc.value)
    assert client.chat.completions.create.call_count == 3


def test_compliance_retry_preserves_reasoning_content():
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(
            json.dumps({"main_line1": "全网第一", "summary": "小牛说：x"}, ensure_ascii=False),
            reasoning_content="secret-trace",
        ),
        _response(_OK_JSON),
    ]
    from utils.forbidden_words import reload_registry

    result, compliance = invoke_json_llm_with_compliance(
        client=client,
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.5,
        max_tokens=2048,
        registry=reload_registry(),
    )

    assert result["main_line1"].startswith("突发")
    assert compliance.retried is True
    retry_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assistant = next(m for m in retry_messages if m.get("role") == "assistant")
    assert assistant["reasoning_content"] == "secret-trace"
