"""First-comment timing and deferred-mode helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.browser_nav import format_network_error_message, open_creator_pages
from services.publishing.browser_session import open_adapter_browser
from services.publishing.first_comment_settings import get_first_comment_settings
from services.publishing.platform_capabilities import get_platform_limits
from services.publishing.publish_warmup import warmup_creator_session


def get_comment_timing(platform_id: str) -> tuple[int, int, bool]:
    """Return (delay_sec, wait_max_sec, deferred) for a platform."""
    fc = get_first_comment_settings()
    limits = get_platform_limits(platform_id)
    try:
        delay = int(limits.get("comment_delay_sec", fc.get("comment_delay_sec", 15)))
    except (TypeError, ValueError):
        delay = 15
    try:
        wait_max = int(limits.get("comment_wait_max_sec", fc.get("comment_wait_max_sec", 60)))
    except (TypeError, ValueError):
        wait_max = 60
    deferred = bool(limits.get("first_comment_deferred", False))
    return max(0, delay), max(15, wait_max), deferred


def is_first_comment_deferred(platform_id: str) -> bool:
    return get_comment_timing(platform_id)[2]


def run_standalone_first_comment(
    session_path: Path,
    *,
    platform_id: str,
    platform_label: str,
    creator_url: str,
    warmup_url: str,
    success_url_excludes: list[str],
    post_fn: Callable[..., CommentResult],
    post_id: str | None,
    post_url: str | None,
    title: str | None,
    text: str,
    delay_sec: int = 15,
    wait_max_sec: int = 60,
    post_id_kw: str = "post_id",
) -> CommentResult:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    kwargs = {
        "text": text,
        "title": (title or "").strip(),
        "delay_sec": delay_sec,
        "wait_max_sec": wait_max_sec,
        post_id_kw: post_id,
    }
    del post_url
    try:
        with open_adapter_browser(session_path, mode="publish") as sess:
            page = sess.page
            if platform_id in {"wechat_channels", "kuaishou"}:
                page.goto(creator_url, wait_until="domcontentloaded", timeout=60_000)
            else:
                open_creator_pages(
                    page,
                    warmup_url=warmup_url,
                    target_url=creator_url,
                    timeout_ms=60_000,
                )
            warmup_creator_session(page, platform_id=platform_id)
            if platform_id == "wechat_channels":
                if "login" in page.url.lower():
                    return CommentResult(success=False, error_message="会话已过期，请重新扫码登录")
            elif not is_login_success_url(page.url, success_url_excludes):
                return CommentResult(success=False, error_message="会话已过期，请重新扫码登录")
            return post_fn(page, **kwargs)
    except PlaywrightTimeoutError as exc:
        return CommentResult(success=False, error_message=str(exc))
    except Exception as exc:
        return CommentResult(
            success=False,
            error_message=format_network_error_message(exc, platform=platform_label),
        )
