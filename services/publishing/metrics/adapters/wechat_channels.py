"""WeChat Channels video metrics parsing and fetch."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from services.publishing.metrics.adapters.base import MetricsAdapter, PostMetricsItem
from services.publishing.metrics.adapters.common import (
    build_post_metrics_items_from_rows,
    extract_funnel_metric_fields,
)
from src.utils.config import Config

POST_LIST_URL = "https://channels.weixin.qq.com/platform/post/list"
POST_LIST_API = "https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/post/post_list"

_FETCH_POST_LIST_JS = """
async ([currentPage, pageSize]) => {
  const resp = await fetch('https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/post/post_list', {
    method: 'POST',
    credentials: 'include',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      currentPage,
      pageSize,
      timestamp: Date.now(),
    }),
  });
  if (!resp.ok) {
    return { error: resp.status, status_text: resp.statusText };
  }
  return await resp.json();
}
"""


def _extract_wechat_title(item: dict[str, Any]) -> str:
    desc = item.get("desc") or {}
    short_titles = desc.get("shortTitle") or []
    if short_titles and isinstance(short_titles[0], dict):
        title = str(short_titles[0].get("shortTitle") or "").strip()
        if title:
            return title
    return str(desc.get("description") or "").strip()


def parse_wechat_post_list_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload or payload.get("error"):
        return []
    if payload.get("errCode") not in (None, 0):
        return []

    data = payload.get("data") or {}
    items = data.get("list") or []
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        export_id = item.get("objectId") or item.get("exportId") or item.get("export_id")
        if not export_id:
            continue
        rows.append(
            {
                "export_id": str(export_id),
                "title": _extract_wechat_title(item),
                "published_at": item.get("createTime"),
                "view_count": item.get("readCount"),
                "like_count": item.get("likeCount"),
                "comment_count": item.get("commentCount"),
                "share_count": item.get("forwardCount"),
                "favorite_count": item.get("favCount"),
                **extract_funnel_metric_fields(item),
            }
        )
    return rows


def probe_wechat_creator_session(session_path: Path, *, headless: bool = True) -> tuple[bool, int | None]:
    """Probe WeChat Channels session via post_list API (same check metrics sync needs)."""
    from playwright.sync_api import sync_playwright

    from services.publishing.human_interaction import human_idle_on_page, open_stealth_browser
    from services.publishing.human_pacing import human_pause
    from services.publishing.session_store import load_encrypted

    temp_state = Config.DATA_DIR / "publish" / "_wechat_probe_state.json"
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
        page.goto(POST_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        payload = page.evaluate(_FETCH_POST_LIST_JS, [1, 1])
        if not isinstance(payload, dict):
            return False, None
        err_code = payload.get("errCode")
        return err_code == 0, err_code
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        temp_state.unlink(missing_ok=True)


def fetch_wechat_metrics_rows(
    session_path: Path,
    *,
    limit: int = 100,
    needed_post_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch WeChat Channels metrics via post_list API."""
    from playwright.sync_api import sync_playwright

    from services.publishing.human_interaction import human_idle_on_page, open_stealth_browser
    from services.publishing.human_pacing import human_pause
    from services.publishing.session_store import load_encrypted

    temp_state = Config.DATA_DIR / "publish" / "_metrics_state.json"
    playwright = None
    browser = None
    captured_payloads: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if "post/post_list" not in response.url or response.status not in (200, 201):
            return
        try:
            payload = response.json()
        except Exception:
            return
        if isinstance(payload, dict) and payload.get("errCode") == 0:
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

        page.goto(POST_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        human_idle_on_page(page, moves=2)

        if "login" in page.url.lower():
            logger.warning("WeChat Channels metrics: session appears logged out")
            return []

        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        def extend_rows(batch: list[dict[str, Any]]) -> None:
            for row in batch:
                export_id = str(row.get("export_id") or "").strip()
                if not export_id or export_id in seen_ids:
                    continue
                seen_ids.add(export_id)
                rows.append(row)

        for payload in captured_payloads:
            extend_rows(parse_wechat_post_list_payload(payload))

        needed = {str(item).strip() for item in (needed_post_ids or set()) if item}
        page_num = 1
        page_size = 20
        max_pages = 15
        while len(rows) < limit or (needed and not needed.issubset(seen_ids)):
            if page_num > max_pages:
                break
            payload = page.evaluate(_FETCH_POST_LIST_JS, [page_num, page_size])
            if not isinstance(payload, dict):
                break
            if payload.get("errCode") not in (None, 0):
                logger.warning(
                    "WeChat post_list API returned errCode={}",
                    payload.get("errCode"),
                )
                break
            batch = parse_wechat_post_list_payload(payload)
            if not batch:
                break
            before = len(rows)
            extend_rows(batch)
            if len(rows) == before:
                break
            data = payload.get("data") or {}
            if not data.get("continueFlag") or len(batch) < page_size:
                break
            page_num += 1
            time.sleep(0.5)

        if rows:
            logger.info("WeChat post_list fetched {} item(s) via API", len(rows))

        logger.info("WeChat Channels metrics fetched {} raw row(s)", len(rows))
        return rows[:limit] if not needed else rows
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        temp_state.unlink(missing_ok=True)


def build_wechat_metrics_items_from_rows(rows: list[dict[str, Any]]) -> list[PostMetricsItem]:
    return build_post_metrics_items_from_rows(
        rows,
        id_keys=("export_id", "object_id", "platform_post_id"),
        post_url_builder=None,
    )


class WechatChannelsMetricsAdapter(MetricsAdapter):
    platform_id = "wechat_channels"

    def fetch_recent_post_metrics(
        self,
        session_path: Path,
        *,
        since_days: int = 90,
        limit: int = 100,
        needed_post_ids: set[str] | None = None,
    ) -> list[PostMetricsItem]:
        del since_days
        rows = fetch_wechat_metrics_rows(
            session_path,
            limit=limit,
            needed_post_ids=needed_post_ids,
        )
        items = build_wechat_metrics_items_from_rows(rows)
        logger.info("WeChat Channels metrics parsed {} item(s)", len(items))
        return items
