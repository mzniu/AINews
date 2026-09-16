"""Kuaishou video metrics parsing and fetch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from services.publishing.metrics.adapters.base import MetricsAdapter, PostMetricsItem
from services.publishing.metrics.adapters.common import (
    MetricsPageInfo,
    build_post_metrics_items_from_rows,
    collect_paginated_rows,
    extract_funnel_metric_fields,
)
from services.publishing.metrics.post_id import build_kuaishou_post_url
from src.utils.config import Config

CONTENT_MANAGE_URL = "https://cp.kuaishou.com/article/manage/video"
PROFILE_URL = "https://cp.kuaishou.com/profile"
PHOTO_LIST_PATH = "/rest/cp/works/v2/video/pc/photo/list"

_EXTRACT_ROWS_JS = """
() => {
  const rows = [];
  const seen = new Set();
  const pushRow = (row) => {
    const id = String(row.photo_id || row.work_id || row.platform_post_id || '').trim();
    if (!id || seen.has(id)) return;
    seen.add(id);
    rows.push(row);
  };

  const html = document.body.innerHTML;
  for (const match of html.matchAll(/workId=([A-Za-z0-9_-]+)/g)) {
    pushRow({ work_id: match[1] });
  }
  for (const match of html.matchAll(/photoId=([A-Za-z0-9_-]+)/g)) {
    pushRow({ photo_id: match[1] });
  }

  document.querySelectorAll('[data-photo-id], [data-work-id]').forEach((el) => {
    const photoId = el.getAttribute('data-photo-id') || el.getAttribute('data-work-id');
    if (!photoId) return;
    const titleEl = el.querySelector('[class*="title"], .title, h3, h4');
    pushRow({
      photo_id: photoId,
      title: titleEl ? titleEl.textContent.trim() : '',
    });
  });
  return rows;
}
"""


def parse_kuaishou_photo_list_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Kuaishou photo/list API payloads into metric rows."""
    if not payload or payload.get("result") != 1:
        return []

    data = payload.get("data") or {}
    items = data.get("list") or []
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        work_id = item.get("workId") or item.get("photoId") or item.get("photo_id")
        if not work_id:
            continue
        rows.append(
            {
                "photo_id": str(work_id),
                "title": str(item.get("title") or "").strip(),
                "published_at": item.get("uploadTime") or item.get("publishTime"),
                "view_count": item.get("playCount") or item.get("viewCount"),
                "like_count": item.get("likeCount"),
                "comment_count": item.get("commentCount"),
                "share_count": item.get("shareCount"),
                **extract_funnel_metric_fields(item),
            }
        )
    return rows


def parse_kuaishou_photo_list_page_info(payload: dict[str, Any]) -> MetricsPageInfo:
    if not payload or payload.get("result") != 1:
        return MetricsPageInfo(has_more=False)
    data = payload.get("data") or {}
    items = data.get("list") or []
    raw_more = data.get("hasMore")
    if raw_more is None:
        raw_more = data.get("has_more")
    total = data.get("total")
    page = data.get("page") or data.get("currentPage")
    page_size = data.get("count") or data.get("pageSize") or 20
    if raw_more is None and total is not None and page is not None:
        try:
            raw_more = int(page) * int(page_size) < int(total)
        except (TypeError, ValueError):
            raw_more = False
    elif raw_more is None:
        try:
            raw_more = len(items) >= int(page_size)
        except (TypeError, ValueError):
            raw_more = False
    has_more = bool(raw_more) and str(raw_more).strip().lower() not in {"0", "false"}
    cursor = data.get("pcursor") or data.get("cursor") or data.get("nextCursor")
    if cursor is None and page is not None:
        try:
            cursor = int(page) + 1
        except (TypeError, ValueError):
            cursor = None
    elif cursor is None and has_more:
        cursor = 2
    return MetricsPageInfo(has_more=has_more, next_cursor=cursor)


_FETCH_PHOTO_LIST_JS = """
async (pageNum) => {
  const url = `/rest/cp/works/v2/video/pc/photo/list?queryType=1&page=${pageNum}&count=20`;
  const resp = await fetch(url, { credentials: 'include' });
  if (!resp.ok) {
    return { error: resp.status };
  }
  return await resp.json();
}
"""


def fetch_kuaishou_metrics_rows(
    session_path: Path,
    *,
    limit: int = 100,
    needed_post_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch Kuaishou metrics by capturing signed photo/list API responses."""
    from playwright.sync_api import sync_playwright

    from services.publishing.human_interaction import human_idle_on_page, open_stealth_browser
    from services.publishing.human_pacing import human_pause
    from services.publishing.session_store import load_encrypted

    temp_state = Config.DATA_DIR / "publish" / "_metrics_state.json"
    playwright = None
    browser = None
    captured_payloads: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if PHOTO_LIST_PATH not in response.url or response.status != 200:
            return
        try:
            payload = response.json()
        except Exception:
            return
        if payload.get("result") == 1:
            captured_payloads.append(payload)

    try:
        temp_state.write_bytes(load_encrypted(session_path))
        playwright = sync_playwright().start()
        browser, context = open_stealth_browser(
            playwright,
            headless=False,
            storage_state=str(temp_state),
        )
        page = context.new_page()
        page.on("response", on_response)

        page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        if "passport.kuaishou.com" in page.url:
            logger.warning("Kuaishou metrics: session appears logged out")
            return []

        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        human_idle_on_page(page, moves=2)

        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        def extend_rows(batch: list[dict[str, Any]]) -> None:
            for row in batch:
                photo_id = str(row.get("photo_id") or row.get("work_id") or "").strip()
                if not photo_id or photo_id in seen_ids:
                    continue
                seen_ids.add(photo_id)
                rows.append(row)

        for payload in captured_payloads:
            extend_rows(parse_kuaishou_photo_list_payload(payload))

        if not rows:
            dom_rows = page.evaluate(_EXTRACT_ROWS_JS) or []
            extend_rows(dom_rows)
            if dom_rows:
                logger.info("Kuaishou metrics DOM fallback fetched {} raw row(s)", len(dom_rows))

        needed = {str(item).strip() for item in (needed_post_ids or set()) if item}

        def fetch_num_page(cursor: Any) -> dict[str, Any] | None:
            payload = page.evaluate(_FETCH_PHOTO_LIST_JS, int(cursor or 1))
            return payload if isinstance(payload, dict) else None

        extend_rows(
            collect_paginated_rows(
                fetch_num_page,
                parse_rows=parse_kuaishou_photo_list_payload,
                parse_page_info=parse_kuaishou_photo_list_page_info,
                row_id=lambda row: str(row.get("photo_id") or ""),
                limit=limit,
                initial_cursor=1,
                needed_ids=needed,
                max_pages=20,
            )
        )

        logger.info("Kuaishou metrics fetched {} raw row(s)", len(rows))
        return rows[:limit] if not needed else rows
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        temp_state.unlink(missing_ok=True)


def build_kuaishou_metrics_items_from_rows(rows: list[dict[str, Any]]) -> list[PostMetricsItem]:
    return build_post_metrics_items_from_rows(
        rows,
        id_keys=("photo_id", "work_id", "platform_post_id"),
        post_url_builder=build_kuaishou_post_url,
    )


class KuaishouMetricsAdapter(MetricsAdapter):
    platform_id = "kuaishou"

    def fetch_recent_post_metrics(
        self,
        session_path: Path,
        *,
        since_days: int = 90,
        limit: int = 100,
        needed_post_ids: set[str] | None = None,
    ) -> list[PostMetricsItem]:
        del since_days
        rows = fetch_kuaishou_metrics_rows(
            session_path,
            limit=limit,
            needed_post_ids=needed_post_ids,
        )
        items = build_kuaishou_metrics_items_from_rows(rows)
        logger.info("Kuaishou metrics parsed {} item(s)", len(items))
        return items
