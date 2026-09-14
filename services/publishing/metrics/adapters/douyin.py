"""Douyin video metrics parsing and fetch."""
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
from services.publishing.metrics.post_id import build_douyin_post_url
from src.utils.config import Config

CONTENT_MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage"
CREATOR_HOME_URL = "https://creator.douyin.com/creator-micro/home"
WORK_LIST_PATH = "/janus/douyin/creator/pc/work_list"

DEFAULT_WORK_LIST_QUERY = {
    "status": 0,
    "count": 20,
    "max_cursor": 0,
    "scene": "star_atlas",
    "device_platform": "android",
    "aid": 1128,
}

_FETCH_WORK_LIST_JS = """
async (params) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    search.set(key, String(value));
  }
  const url = `https://creator.douyin.com/janus/douyin/creator/pc/work_list?${search.toString()}`;
  const resp = await fetch(url, { credentials: 'include' });
  if (!resp.ok) {
    return { error: resp.status, status_text: resp.statusText };
  }
  return await resp.json();
}
"""


def _payload_status_code(payload: dict[str, Any]) -> int | None:
    if "status_code" in payload:
        try:
            return int(payload["status_code"])
        except (TypeError, ValueError):
            return None
    if "result" in payload:
        try:
            return int(payload["result"])
        except (TypeError, ValueError):
            return None
    return None


def _extract_work_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("work_list", "aweme_list", "list", "items"):
            items = data.get(key)
            if isinstance(items, list) and items:
                return items
    for key in ("aweme_list", "items", "work_list"):
        items = payload.get(key)
        if isinstance(items, list) and items:
            return items
    return []


def parse_douyin_work_list_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Douyin creator work_list API payloads into metric rows."""
    if not payload or payload.get("error"):
        return []

    status_code = _payload_status_code(payload)
    if status_code not in (None, 0, 1):
        return []

    rows: list[dict[str, Any]] = []
    for item in _extract_work_items(payload):
        if not isinstance(item, dict):
            continue
        aweme_id = item.get("aweme_id") or item.get("awemeId") or item.get("item_id") or item.get("id")
        if not aweme_id:
            continue
        stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        funnel = extract_funnel_metric_fields(stats, metrics, item)
        rows.append(
            {
                "video_id": str(aweme_id),
                "title": item.get("desc") or item.get("title") or item.get("caption") or "",
                "published_at": (
                    item.get("create_time")
                    or item.get("public_time")
                    or item.get("createTime")
                    or item.get("publish_time")
                ),
                "view_count": (
                    stats.get("play_count")
                    or metrics.get("play_count")
                    or item.get("play_count")
                    or item.get("playCount")
                ),
                "like_count": (
                    stats.get("digg_count")
                    or metrics.get("digg_count")
                    or item.get("digg_count")
                    or item.get("diggCount")
                ),
                "comment_count": stats.get("comment_count") or metrics.get("comment_count") or item.get("comment_count"),
                "share_count": stats.get("share_count") or metrics.get("share_count") or item.get("share_count"),
                "favorite_count": stats.get("collect_count") or metrics.get("collect_count") or item.get("collect_count"),
                **funnel,
            }
        )
    return rows


def parse_douyin_work_list_page_info(payload: dict[str, Any]) -> MetricsPageInfo:
    if not payload or payload.get("error"):
        return MetricsPageInfo(has_more=False)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    def _pick(*keys: str) -> Any:
        for key in keys:
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    raw_more = _pick("has_more", "hasMore")
    if raw_more is None:
        has_more = False
    else:
        has_more = str(raw_more).strip().lower() not in {"0", "false", "none"}
    cursor = _pick("max_cursor", "cursor", "next_cursor")
    return MetricsPageInfo(has_more=has_more, next_cursor=cursor)


def _page_requires_login(page_text: str) -> bool:
    text = page_text or ""
    if "扫码登录" in text and "作品管理" not in text:
        return True
    if "验证码登录" in text and "数据中心" not in text:
        return True
    return False


def probe_douyin_creator_session(
    session_path: Path,
    *,
    headless: bool = True,
) -> tuple[bool, int | None]:
    """Probe Douyin creator session via work_list API (same check metrics sync needs)."""
    from playwright.sync_api import sync_playwright

    from services.publishing.human_interaction import human_idle_on_page, open_stealth_browser
    from services.publishing.human_pacing import human_pause
    from services.publishing.session_store import load_encrypted

    temp_state = Config.DATA_DIR / "publish" / "_douyin_probe_state.json"
    playwright = None
    browser = None
    try:
        temp_state.write_bytes(load_encrypted(session_path))
        playwright = sync_playwright().start()
        browser, context = open_stealth_browser(
            playwright,
            headless=headless,
            storage_state=str(temp_state),
        )
        page = context.new_page()
        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        human_idle_on_page(page, moves=1)
        payload = page.evaluate(_FETCH_WORK_LIST_JS, dict(DEFAULT_WORK_LIST_QUERY))
        if not isinstance(payload, dict):
            return False, None
        status_code = _payload_status_code(payload)
        return status_code == 0, status_code
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        temp_state.unlink(missing_ok=True)


def fetch_douyin_metrics_rows(
    session_path: Path,
    *,
    limit: int = 100,
    needed_post_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch Douyin metrics via creator work_list API, with in-page fetch fallback."""
    from playwright.sync_api import sync_playwright

    from services.publishing.human_interaction import human_idle_on_page, open_stealth_browser
    from services.publishing.human_pacing import human_pause
    from services.publishing.session_store import load_encrypted

    temp_state = Config.DATA_DIR / "publish" / "_metrics_state.json"
    playwright = None
    browser = None
    captured_payloads: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if WORK_LIST_PATH not in response.url or response.status != 200:
            return
        try:
            payload = response.json()
        except Exception:
            return
        if isinstance(payload, dict):
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

        page.goto(CREATOR_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")

        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        human_idle_on_page(page, moves=2)

        page_text = page.evaluate("() => document.body.innerText || ''")
        if _page_requires_login(page_text):
            logger.warning("Douyin metrics: session appears logged out (login page detected)")
            return []

        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        def extend_rows(batch: list[dict[str, Any]]) -> None:
            for row in batch:
                video_id = str(row.get("video_id") or "").strip()
                if not video_id or video_id in seen_ids:
                    continue
                seen_ids.add(video_id)
                rows.append(row)

        for payload in captured_payloads:
            extend_rows(parse_douyin_work_list_payload(payload))

        needed = {str(item).strip() for item in (needed_post_ids or set()) if item}

        def fetch_cursor_page(cursor: Any) -> dict[str, Any] | None:
            query = dict(DEFAULT_WORK_LIST_QUERY)
            query["max_cursor"] = cursor or 0
            payload = page.evaluate(_FETCH_WORK_LIST_JS, query)
            return payload if isinstance(payload, dict) else None

        extend_rows(
            collect_paginated_rows(
                fetch_cursor_page,
                parse_rows=parse_douyin_work_list_payload,
                parse_page_info=parse_douyin_work_list_page_info,
                row_id=lambda row: str(row.get("video_id") or ""),
                limit=limit,
                initial_cursor=0,
                needed_ids=needed,
            )
        )

        if len(rows) < limit or (needed and not needed.issubset(seen_ids)):
            last_page = [1]

            def fetch_num_page(cursor: Any) -> dict[str, Any] | None:
                last_page[0] = int(cursor or 1)
                payload = page.evaluate(
                    _FETCH_WORK_LIST_JS,
                    {"status": 0, "page_size": 20, "page_num": last_page[0]},
                )
                return payload if isinstance(payload, dict) else None

            def page_num_info(payload: dict[str, Any]) -> MetricsPageInfo:
                batch = parse_douyin_work_list_payload(payload)
                return MetricsPageInfo(has_more=len(batch) >= 20, next_cursor=last_page[0] + 1)

            extend_rows(
                collect_paginated_rows(
                    fetch_num_page,
                    parse_rows=parse_douyin_work_list_payload,
                    parse_page_info=page_num_info,
                    row_id=lambda row: str(row.get("video_id") or ""),
                    limit=limit,
                    initial_cursor=1,
                    needed_ids=needed,
                )
            )

        logger.info("Douyin metrics fetched {} raw row(s)", len(rows))
        return rows[:limit] if not needed else rows
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        temp_state.unlink(missing_ok=True)


def build_douyin_metrics_items_from_rows(rows: list[dict[str, Any]]) -> list[PostMetricsItem]:
    return build_post_metrics_items_from_rows(
        rows,
        id_keys=("video_id", "aweme_id", "platform_post_id"),
        post_url_builder=build_douyin_post_url,
    )


class DouyinMetricsAdapter(MetricsAdapter):
    platform_id = "douyin"

    def fetch_recent_post_metrics(
        self,
        session_path: Path,
        *,
        since_days: int = 90,
        limit: int = 100,
        needed_post_ids: set[str] | None = None,
    ) -> list[PostMetricsItem]:
        del since_days
        rows = fetch_douyin_metrics_rows(
            session_path,
            limit=limit,
            needed_post_ids=needed_post_ids,
        )
        items = build_douyin_metrics_items_from_rows(rows)
        logger.info("Douyin metrics parsed {} item(s)", len(items))
        return items
