"""Kuaishou creator first-comment automation."""
from __future__ import annotations

from typing import Any

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.creator_comment_helpers import (
    dismiss_overlays,
    fill_and_submit_comment,
    open_work_detail,
    wait_for_work,
)
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.kuaishou import (
    CONTENT_MANAGE_URL,
    _FETCH_PHOTO_LIST_JS,
    parse_kuaishou_photo_list_payload,
)
from services.publishing.metrics.post_id import is_synthetic_platform_post_id

if True:
    from playwright.sync_api import Page

DETAIL_URL_TEMPLATES = (
    "https://cp.kuaishou.com/article/manage/video/detail?photoId={photo_id}",
    "https://cp.kuaishou.com/article/manage/video/detail?workId={photo_id}",
)


def _fetch_work_rows(page: Page) -> list[dict[str, Any]]:
    payload = page.evaluate(_FETCH_PHOTO_LIST_JS, 1)
    if isinstance(payload, dict):
        rows = parse_kuaishou_photo_list_payload(payload)
        if rows:
            return rows
    from services.publishing.metrics.adapters.kuaishou import _EXTRACT_ROWS_JS

    dom_rows = page.evaluate(_EXTRACT_ROWS_JS) or []
    return dom_rows if isinstance(dom_rows, list) else []


def post_kuaishou_first_comment(
    page: Page,
    *,
    text: str,
    title: str,
    photo_id: str | None = None,
    delay_sec: int = 15,
    wait_max_sec: int = 60,
) -> CommentResult:
    cleaned = (text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_comment_text")

    real_id = None if is_synthetic_platform_post_id(photo_id) else photo_id
    work = {"photo_id": real_id, "title": title}
    if real_id:
        work["photo_id"] = real_id
        if open_work_detail(page, work, detail_urls=list(DETAIL_URL_TEMPLATES)):
            return fill_and_submit_comment(page, cleaned, platform_label="快手")

    polled = wait_for_work(
        page,
        list_url=CONTENT_MANAGE_URL,
        fetch_rows=_fetch_work_rows,
        title=title,
        post_id=real_id,
        delay_sec=delay_sec if not real_id else 0,
        wait_max_sec=wait_max_sec,
        id_keys=("photo_id", "work_id"),
    )
    if polled is None:
        return CommentResult(success=False, error_message="work_not_found")

    if not open_work_detail(page, polled, detail_urls=list(DETAIL_URL_TEMPLATES)):
        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        dismiss_overlays(page)
        if not open_work_detail(page, polled, detail_urls=[]):
            return CommentResult(success=False, error_message="navigation_failed")

    return fill_and_submit_comment(page, cleaned, platform_label="快手")
