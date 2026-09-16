"""Tests for publish browser navigation helpers."""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from services.publishing.browser_nav import (
    format_network_error_message,
    goto_with_retry,
    is_transient_network_error,
    open_creator_pages,
)


def test_is_transient_network_error():
    assert is_transient_network_error(RuntimeError("Page.goto: net::ERR_ADDRESS_UNREACHABLE at https://x"))
    assert not is_transient_network_error(RuntimeError("会话已过期"))


def test_format_network_error_message():
    msg = format_network_error_message(
        RuntimeError("net::ERR_ADDRESS_UNREACHABLE"),
        platform="抖音",
    )
    assert "抖音" in msg
    assert "网络" in msg


def test_goto_with_retry_retries_transient_errors(monkeypatch):
    page = MagicMock()
    calls = {"count": 0}

    def fake_goto(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("net::ERR_ADDRESS_UNREACHABLE")
        return None

    page.goto.side_effect = fake_goto
    monkeypatch.setattr("services.publishing.browser_nav.time.sleep", lambda _s: None)
    goto_with_retry(page, "https://creator.douyin.com/", retries=3)
    assert page.goto.call_count == 3


def test_goto_with_retry_raises_non_network_error_immediately():
    page = MagicMock()
    page.goto.side_effect = RuntimeError("selector not found")
    with pytest.raises(RuntimeError, match="selector"):
        goto_with_retry(page, "https://example.com", retries=3)
    assert page.goto.call_count == 1


def test_open_creator_pages_visits_warmup_then_target():
    page = MagicMock()
    open_creator_pages(
        page,
        warmup_url="https://creator.douyin.com/creator-micro/home",
        target_url="https://creator.douyin.com/creator-micro/content/upload",
        timeout_ms=1000,
    )
    assert page.goto.call_count == 2
    assert page.goto.call_args_list[0] == call(
        "https://creator.douyin.com/creator-micro/home",
        wait_until="domcontentloaded",
        timeout=1000,
    )
