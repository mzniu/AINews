"""Douyin creator first-comment automation (spike-validated selectors)."""
from __future__ import annotations

import time
from typing import Any

from loguru import logger

from services.publishing.adapters.base import CommentResult
from services.publishing.human_form import human_fill
from services.publishing.human_interaction import human_click
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.douyin import (
    CONTENT_MANAGE_URL,
    DEFAULT_WORK_LIST_QUERY,
    _FETCH_WORK_LIST_JS,
    parse_douyin_work_list_payload,
)

if True:
    from playwright.sync_api import Page

COMMENT_INPUT_SELECTORS = (
    'div.input-d24X73',
    '[placeholder*="有爱评论"]',
    'textarea[placeholder*="评论"]',
    'div[contenteditable="true"][data-placeholder*="说"]',
    '[contenteditable="true"]',
)

COMMENT_SUBMIT_SELECTORS = (
    'button:has-text("发送")',
    'span:has-text("发送")',
)


def _dismiss_overlays(page: Page) -> None:
    for text in ("跳过", "我知道了", "关闭", "下次再说"):
        try:
            btn = page.get_by_text(text, exact=False)
            if btn.count() > 0 and btn.first.is_visible(timeout=400):
                btn.first.click(timeout=2000)
                human_pause(page, "after_click")
        except Exception:
            continue


def _input_hint_excluded(hint: str) -> bool:
    lowered = (hint or "").lower()
    return any(token in lowered for token in ("搜索", "作品", "search"))


def _find_comment_input(page: Page):
    for selector in COMMENT_INPUT_SELECTORS:
        loc = page.locator(selector)
        try:
            count = loc.count()
        except Exception:
            continue
        for idx in range(min(count, 5)):
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
            if selector == 'div.input-d24X73' or any(
                token in (hint or "") for token in ("评论", "说点", "有爱", "留下")
            ):
                return item
    return None


def _find_submit_button(page: Page):
    for selector in COMMENT_SUBMIT_SELECTORS:
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=800):
                return loc.first
        except Exception:
            continue
    return None


def _fetch_work_rows(page: Page) -> list[dict[str, Any]]:
    payload = page.evaluate(_FETCH_WORK_LIST_JS, dict(DEFAULT_WORK_LIST_QUERY))
    if not isinstance(payload, dict):
        return []
    return parse_douyin_work_list_payload(payload)


def _pick_work(rows: list[dict[str, Any]], *, title: str, video_id: str | None) -> dict[str, Any] | None:
    if video_id:
        for row in rows:
            if str(row.get("video_id") or "") == str(video_id):
                return row
    needle = title.strip().lower()
    if needle:
        for row in rows:
            hay = str(row.get("title") or "").lower()
            if needle in hay or hay in needle:
                return row
    return rows[0] if rows else None


def _locate_work_row(page: Page, work: dict[str, Any]):
    title_short = str(work.get("title") or "").strip()[:20]
    if not title_short:
        return None
    for selector in (
        f'[class*="content"]:has-text("{title_short}")',
        f'[class*="item"]:has-text("{title_short}")',
        f'tr:has-text("{title_short}")',
    ):
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible(timeout=1500):
                return loc
        except Exception:
            continue
    return None


def _open_comment_page_for_work(page: Page, work: dict[str, Any]) -> bool:
    video_id = str(work.get("video_id") or "").strip()
    if video_id:
        url = (
            "https://creator.douyin.com/creator-micro/interactive/comment"
            f"?item_id={video_id}"
        )
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        human_pause(page, "page_load")
        _dismiss_overlays(page)
        if _find_comment_input(page) is not None:
            return True

    page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    human_pause(page, "page_load")
    _dismiss_overlays(page)
    row = _locate_work_row(page, work)
    if row is None:
        return False
    comment_count = work.get("comment_count")
    if comment_count is not None:
        try:
            stat = row.get_by_text(str(comment_count), exact=True)
            if stat.count() > 0 and stat.first.is_visible(timeout=1200):
                stat.first.click(timeout=4000)
                human_pause(page, "after_click")
                return _find_comment_input(page) is not None
        except Exception:
            pass
    title_short = str(work.get("title") or "").strip()[:20]
    try:
        title_loc = row.get_by_text(title_short, exact=False).first
        if title_loc.count() > 0 and title_loc.is_visible(timeout=1500):
            title_loc.click(timeout=5000)
            human_pause(page, "page_load")
            return _find_comment_input(page) is not None
    except Exception:
        pass
    return False


def _wait_for_work(
    page: Page,
    *,
    title: str,
    video_id: str | None,
    delay_sec: int,
    wait_max_sec: int,
) -> dict[str, Any] | None:
    if delay_sec > 0:
        time.sleep(delay_sec)
    deadline = time.time() + wait_max_sec
    page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    human_pause(page, "page_load")
    while time.time() <= deadline:
        rows = _fetch_work_rows(page)
        work = _pick_work(rows, title=title, video_id=video_id)
        if work is not None:
            return work
        human_pause(page, "polling")
        time.sleep(5)
    return None


def post_douyin_first_comment(
    page: Page,
    *,
    text: str,
    title: str,
    video_id: str | None = None,
    delay_sec: int = 15,
    wait_max_sec: int = 60,
) -> CommentResult:
    """Post author first comment on a published Douyin work (same browser session)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_comment_text")

    from services.publishing.metrics.post_id import is_synthetic_platform_post_id

    real_video_id = None if is_synthetic_platform_post_id(video_id) else video_id
    work = {"video_id": real_video_id, "title": title}
    if real_video_id:
        work["video_id"] = real_video_id
        if not _open_comment_page_for_work(page, work):
            polled = _wait_for_work(
                page,
                title=title,
                video_id=real_video_id,
                delay_sec=delay_sec,
                wait_max_sec=wait_max_sec,
            )
            if polled is None:
                return CommentResult(success=False, error_message="work_not_found")
            if not _open_comment_page_for_work(page, polled):
                return CommentResult(success=False, error_message="navigation_failed")
    else:
        polled = _wait_for_work(
            page,
            title=title,
            video_id=None,
            delay_sec=delay_sec,
            wait_max_sec=wait_max_sec,
        )
        if polled is None:
            return CommentResult(success=False, error_message="work_not_found")
        if not _open_comment_page_for_work(page, polled):
            return CommentResult(success=False, error_message="navigation_failed")

    comment_input = _find_comment_input(page)
    if comment_input is None:
        return CommentResult(success=False, error_message="comment_input_not_found")

    try:
        human_fill(page, comment_input, cleaned)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"fill_failed:{exc}")

    submit = _find_submit_button(page)
    if submit is None:
        return CommentResult(success=False, error_message="submit_button_not_found")

    try:
        human_click(page, submit, timeout_ms=8000)
        human_pause(page, "after_click")
    except Exception as exc:
        return CommentResult(success=False, error_message=f"submit_click_failed:{exc}")

    logger.info("抖音首评已提交 title={}", title[:40])
    return CommentResult(success=True)
