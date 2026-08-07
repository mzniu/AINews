"""Shared helpers for clicking publish buttons on creator center pages."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from playwright.sync_api import Page

DEFAULT_PUBLISH_TEXTS = ("发表", "发布", "立即发布")

DEFAULT_SUCCESS_PATTERN = re.compile(
    r"发布成功|发表成功|提交成功|已发布|发布完成|作品已发布",
    re.I,
)


def scroll_to_publish_area(page: Page) -> None:
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(600)


def _is_disabled_button(locator) -> bool:
    try:
        return bool(
            locator.evaluate(
                "(el) => Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true')"
            )
        )
    except Exception:
        return False


def _click_visible_publish_candidate(page: Page, locator) -> bool:
    count = locator.count()
    if count == 0:
        return False
    start = max(0, count - 4)
    for index in range(start, count):
        candidate = locator.nth(index)
        try:
            if not candidate.is_visible(timeout=800):
                continue
            if _is_disabled_button(candidate):
                continue
            candidate.scroll_into_view_if_needed(timeout=5000)
            candidate.click(timeout=8000)
            return True
        except Exception:
            continue
    return False


def click_publish_button(
    page: Page,
    *,
    timeout_ms: int,
    button_texts: tuple[str, ...] = DEFAULT_PUBLISH_TEXTS,
    extra_selectors: tuple[str, ...] = (),
    scroll_first: bool = True,
) -> bool:
    if scroll_first:
        scroll_to_publish_area(page)

    deadline_attempts = max(3, timeout_ms // 5000)
    for _ in range(deadline_attempts):
        for selector in extra_selectors:
            try:
                locator = page.locator(selector)
                if _click_visible_publish_candidate(page, locator):
                    logger.info("Clicked publish button via selector %s", selector)
                    page.wait_for_timeout(800)
                    return True
            except Exception:
                continue

        for text in button_texts:
            try:
                role_btn = page.get_by_role("button", name=re.compile(rf"^{re.escape(text)}$"))
                if _click_visible_publish_candidate(page, role_btn):
                    logger.info("Clicked publish button via role (%s)", text)
                    page.wait_for_timeout(800)
                    return True
            except Exception:
                pass
            try:
                css_btn = page.locator("button").filter(
                    has_text=re.compile(rf"^{re.escape(text)}$")
                )
                if _click_visible_publish_candidate(page, css_btn):
                    logger.info("Clicked publish button via css (%s)", text)
                    page.wait_for_timeout(800)
                    return True
            except Exception:
                pass

        try:
            primary = page.locator(
                'button[class*="primary"], button[class*="Primary"]'
            ).filter(has_text=re.compile(r"发布|发表"))
            if _click_visible_publish_candidate(page, primary):
                logger.info("Clicked publish button via primary class")
                page.wait_for_timeout(800)
                return True
        except Exception:
            pass

        page.wait_for_timeout(1500)
    return False


def confirm_publish_dialogs(page: Page, *, timeout_ms: int = 10_000) -> bool:
    confirm_labels = ("确定", "确认", "发布", "发表", "继续发布")
    confirmed = False
    try:
        modal = page.locator(
            '.semi-modal-content, [role="dialog"], [class*="modal"], [class*="Modal"]'
        )
        if modal.count() == 0:
            return False
        for label in confirm_labels:
            try:
                target = modal.last.locator("button").filter(
                    has_text=re.compile(re.escape(label))
                ).first
                if target.is_visible(timeout=min(timeout_ms, 2000)):
                    target.click(timeout=5000)
                    page.wait_for_timeout(800)
                    confirmed = True
                    break
            except Exception:
                continue
    except Exception:
        return False
    return confirmed


def wait_for_publish_success(
    page: Page,
    *,
    timeout_ms: int,
    success_pattern: re.Pattern[str] | None = None,
    success_url_hints: tuple[str, ...] | None = None,
) -> bool:
    pattern = success_pattern or DEFAULT_SUCCESS_PATTERN
    deadline_attempts = max(5, timeout_ms // 3000)
    initial_url = page.url.lower()

    for _ in range(deadline_attempts):
        try:
            if page.get_by_text(pattern).first.is_visible(timeout=1000):
                return True
        except Exception:
            pass

        try:
            body_text = page.evaluate("() => document.body.innerText || ''")
            if body_text and pattern.search(body_text):
                return True
        except Exception:
            pass

        current_url = page.url.lower()
        if success_url_hints:
            if any(hint.lower() in current_url for hint in success_url_hints):
                return True

        if current_url != initial_url:
            if not any(token in current_url for token in ("publish", "upload", "create", "post")):
                return True

        confirm_publish_dialogs(page, timeout_ms=3000)
        page.wait_for_timeout(2000)

    return False


def click_publish_and_wait(
    page: Page,
    *,
    timeout_ms: int,
    button_texts: tuple[str, ...] = DEFAULT_PUBLISH_TEXTS,
    extra_selectors: tuple[str, ...] = (),
    success_pattern: re.Pattern[str] | None = None,
    success_url_hints: tuple[str, ...] | None = None,
    before_click: Callable[[Page], None] | None = None,
) -> bool:
    if before_click is not None:
        before_click(page)
    if not click_publish_button(
        page,
        timeout_ms=min(timeout_ms, 30_000),
        button_texts=button_texts,
        extra_selectors=extra_selectors,
    ):
        return False
    confirm_publish_dialogs(page, timeout_ms=10_000)
    page.wait_for_timeout(1500)
    confirm_publish_dialogs(page, timeout_ms=5000)
    return wait_for_publish_success(
        page,
        timeout_ms=timeout_ms,
        success_pattern=success_pattern,
        success_url_hints=success_url_hints,
    )
