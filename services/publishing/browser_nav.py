"""Playwright navigation helpers with retry for transient network errors."""
from __future__ import annotations

import time
from typing import Any

from services.publishing.human_pacing import human_pause

NETWORK_ERROR_MARKERS = (
    "ERR_ADDRESS_UNREACHABLE",
    "ERR_CONNECTION_REFUSED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_NETWORK_CHANGED",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_TIMED_OUT",
    "net::ERR_",
)


def is_transient_network_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in NETWORK_ERROR_MARKERS)


def format_network_error_message(exc: BaseException, *, platform: str) -> str:
    if is_transient_network_error(exc):
        return (
            f"无法连接{platform}创作者中心（网络不可达或暂时中断）。"
            "请检查本机网络、代理/VPN、防火墙后，在发布中心重试该任务。"
        )
    return str(exc)


def goto_with_retry(
    page: Any,
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 60_000,
    retries: int = 3,
    backoff_sec: float = 2.0,
) -> None:
    last_exc: BaseException | None = None
    for attempt in range(max(1, retries)):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return
        except Exception as exc:
            last_exc = exc
            if not is_transient_network_error(exc) or attempt >= retries - 1:
                raise
            time.sleep(backoff_sec * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def open_creator_pages(
    page: Any,
    *,
    warmup_url: str,
    target_url: str,
    timeout_ms: int = 60_000,
) -> None:
    """Visit home/dashboard first, then the publish/upload page."""
    goto_with_retry(page, warmup_url, timeout_ms=timeout_ms)
    human_pause(page, "page_load")
    if warmup_url.rstrip("/") != target_url.rstrip("/"):
        goto_with_retry(page, target_url, timeout_ms=timeout_ms)
    human_pause(page, "page_load")
