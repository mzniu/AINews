"""Shared helpers for creator-center first-comment automation."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from services.publishing.adapters.base import CommentResult
from services.publishing.human_form import human_fill
from services.publishing.human_interaction import human_click
from services.publishing.human_pacing import human_pause

if TYPE_CHECKING:
    from playwright.sync_api import Page

COMMENT_INPUT_SELECTORS = (
    'textarea[placeholder*="评论"]',
    'textarea[placeholder*="说点什么"]',
    'textarea[placeholder*="友善"]',
    'textarea[placeholder*="留下"]',
    'input[placeholder*="评论"]',
    'div[contenteditable="true"][data-placeholder*="评论"]',
    'div[contenteditable="true"][data-placeholder*="说"]',
    'div[contenteditable="true"][data-placeholder*="留下"]',
    '[aria-label*="评论"]',
    '[placeholder*="留下你的精彩评论"]',
    '[data-e2e="comment-input"] [contenteditable="true"]',
    '[class*="comment"] [contenteditable="true"]',
    '[contenteditable="true"]',
)

COMMENT_SUBMIT_SELECTORS = (
    'button:has-text("发送")',
    'button:has-text("发布")',
    'button:has-text("评论")',
    'span:has-text("发送")',
)


def dismiss_overlays(page: Page) -> None:
    for text in ("跳过", "我知道了", "关闭", "下次再说", "知道了"):
        try:
            btn = page.get_by_text(text, exact=False)
            if btn.count() > 0 and btn.first.is_visible(timeout=400):
                btn.first.click(timeout=2000)
                human_pause(page, "after_click")
        except Exception:
            continue


def _input_hint_excluded(hint: str) -> bool:
    lowered = (hint or "").lower()
    return any(token in lowered for token in ("搜索", "作品", "search", "标题"))


def find_comment_input(page: Page):
    for selector in COMMENT_INPUT_SELECTORS:
        loc = page.locator(selector)
        try:
            count = loc.count()
        except Exception:
            continue
        for idx in range(min(count, 6)):
            item = loc.nth(idx)
            try:
                if not item.is_visible(timeout=500):
                    continue
            except Exception:
                continue
            hint = item.evaluate(
                """(el) => [
                  el.getAttribute('placeholder'),
                  el.getAttribute('data-placeholder'),
                  el.getAttribute('aria-label'),
                ].filter(Boolean).join(' ')"""
            )
            if _input_hint_excluded(hint):
                continue
            if any(token in (hint or "") for token in ("评论", "说点", "留下", "友善", "互动")):
                return item
            if selector.endswith('[contenteditable="true"]'):
                return item
    return None


def find_submit_button(page: Page):
    for selector in COMMENT_SUBMIT_SELECTORS:
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=800):
                return loc.first
        except Exception:
            continue
    return None


def pick_work(
    rows: list[dict[str, Any]],
    *,
    title: str,
    post_id: str | None,
    id_keys: tuple[str, ...] = ("photo_id", "work_id", "note_id", "export_id", "video_id"),
) -> dict[str, Any] | None:
    if post_id:
        for row in rows:
            for key in id_keys:
                if str(row.get(key) or "") == str(post_id):
                    return row
    needle = title.strip().lower()
    if needle:
        for row in rows:
            hay = str(row.get("title") or "").lower()
            if needle in hay or hay in needle:
                return row
    return rows[0] if rows else None


def locate_work_row(page: Page, work: dict[str, Any], *, title_chars: int = 20):
    title_short = str(work.get("title") or "").strip()[:title_chars]
    if not title_short:
        return None
    for selector in (
        f'[class*="content"]:has-text("{title_short}")',
        f'[class*="item"]:has-text("{title_short}")',
        f'tr:has-text("{title_short}")',
        f'a:has-text("{title_short}")',
    ):
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible(timeout=1500):
                return loc
        except Exception:
            continue
    return None


def wait_for_work(
    page: Page,
    *,
    list_url: str,
    fetch_rows: Callable[[Page], list[dict[str, Any]]],
    title: str,
    post_id: str | None,
    delay_sec: int,
    wait_max_sec: int,
    id_keys: tuple[str, ...] = ("photo_id", "work_id", "note_id", "export_id", "video_id"),
) -> dict[str, Any] | None:
    if delay_sec > 0:
        time.sleep(delay_sec)
    deadline = time.time() + wait_max_sec
    page.goto(list_url, wait_until="domcontentloaded", timeout=60_000)
    human_pause(page, "page_load")
    dismiss_overlays(page)
    while time.time() <= deadline:
        rows = fetch_rows(page)
        work = pick_work(rows, title=title, post_id=post_id, id_keys=id_keys)
        if work is not None:
            return work
        human_pause(page, "polling")
        time.sleep(5)
        try:
            page.reload(wait_until="domcontentloaded", timeout=45_000)
        except Exception:
            pass
    return None


def open_work_detail(page: Page, work: dict[str, Any], *, detail_urls: list[str]) -> bool:
    for template in detail_urls:
        url = template
        for key, value in work.items():
            if value is None:
                continue
            url = url.replace(f"{{{key}}}", str(value))
        if "{" in url:
            continue
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        human_pause(page, "page_load")
        dismiss_overlays(page)
        if find_comment_input(page) is not None:
            return True

    row = locate_work_row(page, work)
    if row is not None:
        try:
            row.click(timeout=5000)
            human_pause(page, "page_load")
            if find_comment_input(page) is not None:
                return True
        except Exception:
            pass
        title_short = str(work.get("title") or "").strip()[:20]
        if title_short:
            try:
                title_loc = row.get_by_text(title_short, exact=False).first
                if title_loc.count() > 0 and title_loc.is_visible(timeout=1500):
                    title_loc.click(timeout=5000)
                    human_pause(page, "page_load")
                    if find_comment_input(page) is not None:
                        return True
            except Exception:
                pass
    return False


def fill_and_submit_comment(page: Page, text: str, *, platform_label: str) -> CommentResult:
    cleaned = (text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_comment_text")

    comment_input = find_comment_input(page)
    if comment_input is None:
        return CommentResult(success=False, error_message="comment_input_not_found")

    try:
        human_fill(page, comment_input, cleaned)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"fill_failed:{exc}")

    submit = find_submit_button(page)
    if submit is None:
        return CommentResult(success=False, error_message="submit_button_not_found")

    try:
        human_click(page, submit, timeout_ms=8000)
        human_pause(page, "after_click")
    except Exception as exc:
        return CommentResult(success=False, error_message=f"submit_click_failed:{exc}")

    logger.info("{}首评已提交", platform_label)
    return CommentResult(success=True)
