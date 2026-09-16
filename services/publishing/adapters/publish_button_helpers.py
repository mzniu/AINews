"""Shared helpers for clicking publish buttons on creator center pages."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from services.publishing.human_pacing import human_pause

if TYPE_CHECKING:
    from playwright.sync_api import Page

DEFAULT_PUBLISH_TEXTS = ("发表", "发布", "立即发布")

DEFAULT_SUCCESS_PATTERN = re.compile(
    r"发布成功|发表成功|提交成功|已发布|发布完成|作品已发布|发表完成|已提交",
    re.I,
)


def collect_visible_text(page: Page) -> str:
    """Collect visible text including open shadow roots (e.g. wujie-app)."""
    try:
        return page.evaluate(
            """() => {
                const chunks = [];
                const seen = new Set();
                const walk = (root) => {
                    if (!root || seen.has(root)) return;
                    seen.add(root);
                    if (root.innerText) chunks.push(root.innerText);
                    if (root.shadowRoot) walk(root.shadowRoot);
                    if (root.querySelectorAll) {
                        for (const node of root.querySelectorAll('*')) {
                            if (node.shadowRoot) walk(node.shadowRoot);
                        }
                    }
                };
                walk(document.body);
                const wujie = document.querySelector('wujie-app');
                if (wujie) walk(wujie);
                return chunks.join('\\n');
            }"""
        ) or ""
    except Exception:
        return ""


def url_suggests_publish_success(initial_url: str, current_url: str) -> bool:
    """Heuristic: left the publish/create editor page."""
    initial = initial_url.lower()
    current = current_url.lower()
    if current == initial:
        return False
    if "post/create" in initial and "post/create" not in current:
        return True
    if any(hint in current for hint in ("post/list", "post/manage", "content/manage")):
        return True
    blocked = ("/publish", "/upload", "/create", "post/create")
    if any(token in current for token in blocked):
        return False
    return not any(token in current for token in ("publish", "upload", "create"))


def scroll_to_publish_area(page: Page) -> None:
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    human_pause(page, "after_click")


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
    post_click_pause: bool = True,
) -> bool:
    if scroll_first:
        scroll_to_publish_area(page)

    deadline_attempts = max(3, timeout_ms // 5000)
    for _ in range(deadline_attempts):
        for selector in extra_selectors:
            try:
                locator = page.locator(selector)
                if _click_visible_publish_candidate(page, locator):
                    logger.info("Clicked publish button via selector {}", selector)
                    if post_click_pause:
                        human_pause(page, "after_click")
                    else:
                        page.wait_for_timeout(400)
                    return True
            except Exception:
                continue

        for text in button_texts:
            try:
                role_btn = page.get_by_role("button", name=re.compile(rf"^{re.escape(text)}$"))
                if _click_visible_publish_candidate(page, role_btn):
                    logger.info("Clicked publish button via role ({})", text)
                    if post_click_pause:
                        human_pause(page, "after_click")
                    else:
                        page.wait_for_timeout(400)
                    return True
            except Exception:
                pass
            try:
                css_btn = page.locator("button").filter(
                    has_text=re.compile(rf"^{re.escape(text)}$")
                )
                if _click_visible_publish_candidate(page, css_btn):
                    logger.info("Clicked publish button via css ({})", text)
                    if post_click_pause:
                        human_pause(page, "after_click")
                    else:
                        page.wait_for_timeout(400)
                    return True
            except Exception:
                pass

        try:
            primary = page.locator(
                'button[class*="primary"], button[class*="Primary"]'
            ).filter(has_text=re.compile(r"发布|发表"))
            if _click_visible_publish_candidate(page, primary):
                logger.info("Clicked publish button via primary class")
                if post_click_pause:
                    human_pause(page, "after_click")
                else:
                    page.wait_for_timeout(400)
                return True
        except Exception:
            pass

        human_pause(page, "polling")
    return False


def confirm_publish_dialogs(page: Page, *, timeout_ms: int = 10_000) -> bool:
    confirm_labels = ("确定", "确认", "确认发布", "确定发布", "发布", "发表", "继续发布", "我知道了", "知道了")
    confirmed = False
    modal_selectors = (
        '.semi-modal-content',
        '.d-modal',
        '.d-dialog',
        '[role="dialog"]',
        '[class*="modal"]',
        '[class*="Modal"]',
        '[class*="dialog"]',
        '[class*="Dialog"]',
        '.el-dialog',
        '.el-message-box',
    )
    try:
        modal = None
        for selector in modal_selectors:
            locator = page.locator(selector)
            if locator.count() > 0:
                modal = locator.last
                break
        if modal is None:
            return False
        for label in confirm_labels:
            try:
                target = modal.locator("button").filter(
                    has_text=re.compile(re.escape(label))
                ).first
                if target.is_visible(timeout=min(timeout_ms, 2000)):
                    target.click(timeout=5000)
                    human_pause(page, "modal")
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
    failure_pattern: re.Pattern[str] | None = None,
    initial_url: str | None = None,
    url_success_checker: Callable[[str, str], bool] | None = None,
) -> bool:
    pattern = success_pattern or DEFAULT_SUCCESS_PATTERN
    deadline_attempts = max(5, timeout_ms // 3000)
    initial_url = initial_url or page.url
    initial_url_lower = initial_url.lower()

    for attempt in range(deadline_attempts):
        visible_text = collect_visible_text(page)
        if failure_pattern and visible_text and failure_pattern.search(visible_text):
            logger.warning("Publish failure detected in page text")
            return False

        try:
            if page.get_by_text(pattern).first.is_visible(timeout=800):
                logger.info("Publish success detected via visible text")
                return True
        except Exception:
            pass

        try:
            wujie_text = page.locator("wujie-app").inner_text(timeout=1000)
            if wujie_text:
                if failure_pattern and failure_pattern.search(wujie_text):
                    logger.warning("Publish failure detected in wujie-app text")
                    return False
                if pattern.search(wujie_text):
                    logger.info("Publish success detected in wujie-app text")
                    return True
        except Exception:
            pass

        if visible_text and pattern.search(visible_text):
            logger.info("Publish success detected in page/shadow text")
            return True

        current_url = page.url
        current_url_lower = current_url.lower()
        if success_url_hints:
            if any(hint.lower() in current_url_lower for hint in success_url_hints):
                logger.info("Publish success detected via URL hint: {}", current_url)
                return True

        if url_success_checker and url_success_checker(initial_url_lower, current_url_lower):
            logger.info("Publish success detected via custom URL checker: {} -> {}", initial_url, current_url)
            return True

        if url_suggests_publish_success(initial_url_lower, current_url_lower):
            logger.info("Publish success detected via URL change: {} -> {}", initial_url, current_url)
            return True

        confirm_publish_dialogs(page, timeout_ms=3000)
        if attempt < 12:
            page.wait_for_timeout(900)
        else:
            human_pause(page, "polling")

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
    human_pause(page, "before_publish")
    if not click_publish_button(
        page,
        timeout_ms=min(timeout_ms, 30_000),
        button_texts=button_texts,
        extra_selectors=extra_selectors,
        post_click_pause=False,
    ):
        return False
    confirm_publish_dialogs(page, timeout_ms=10_000)
    human_pause(page, "modal")
    confirm_publish_dialogs(page, timeout_ms=5000)
    return wait_for_publish_success(
        page,
        timeout_ms=timeout_ms,
        success_pattern=success_pattern,
        success_url_hints=success_url_hints,
    )
