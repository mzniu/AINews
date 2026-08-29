"""Shared metrics parsing and browser fetch helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from services.publishing.metrics.adapters.base import PostMetricsItem

_CLICK_NEXT_PAGE_JS = """
() => {
  const next = document.querySelector(
    '.ant-pagination-next:not(.ant-pagination-disabled), .el-pagination .btn-next:not([disabled])'
  );
  if (next) {
    next.click();
    return 'pager';
  }
  const els = Array.from(document.querySelectorAll('button, a, li, span'));
  for (const el of els) {
    const text = (el.innerText || el.getAttribute('aria-label') || '').trim();
    if ((text === '下一页' || text === '下页' || text === '>' || text === '›') && !el.disabled) {
      el.click();
      return 'text';
    }
  }
  return '';
}
"""


@dataclass(frozen=True)
class MetricsPageInfo:
    has_more: bool
    next_cursor: Any = None


def collect_paginated_rows(
    fetch_page: Callable[[Any], Any],
    *,
    parse_rows: Callable[[Any], list[dict[str, Any]]],
    parse_page_info: Callable[[Any], MetricsPageInfo],
    row_id: Callable[[dict[str, Any]], str],
    limit: int,
    initial_cursor: Any = 0,
    max_pages: int = 15,
    needed_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch list pages until `limit` or `needed_ids` are collected."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = initial_cursor
    needed = {str(item).strip() for item in (needed_ids or set()) if item}

    for _ in range(max(1, max_pages)):
        payload = fetch_page(cursor)
        if payload is None:
            break
        for row in parse_rows(payload) or []:
            rid = str(row_id(row) or "").strip()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            rows.append(row)
        have_needed = not needed or needed.issubset(seen)
        if len(rows) >= limit and have_needed:
            break
        info = parse_page_info(payload)
        if not info.has_more:
            break
        if info.next_cursor is None or info.next_cursor == cursor:
            break
        cursor = info.next_cursor

    if needed:
        return rows
    return rows[:limit]


def metric_row_id(row: dict[str, Any]) -> str:
    for key in ("video_id", "note_id", "photo_id", "work_id", "export_id", "platform_post_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def parse_count_text(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"—", "-", "暂无", "null", "None"}:
        return None
    try:
        if text.endswith("万"):
            return int(float(text[:-1]) * 10000)
        if text.endswith("亿"):
            return int(float(text[:-1]) * 100000000)
        if text.endswith("w") or text.endswith("W"):
            return int(float(text[:-1]) * 10000)
        return int(float(text))
    except ValueError:
        return None


FOLLOW_COUNT_KEYS = (
    "follow_count",
    "fans_count",
    "new_fans",
    "increase_fans",
    "follower_count",
    "followCount",
)
PLAY_3S_RATE_KEYS = (
    "play_3s_rate",
    "play_3s_ratio",
    "three_seconds_rate",
    "vv_3s_rate",
    "play3sRate",
)
COMPLETION_RATE_KEYS = (
    "completion_rate",
    "finish_rate",
    "play_finish_rate",
    "complete_rate",
    "play_over_rate",
    "fullPlayRate",
    "finishPlayRate",
)
AVG_WATCH_KEYS = (
    "avg_watch_sec",
    "avg_play_duration",
    "avg_watch_duration",
    "play_duration",
    "avgPlayTimeSec",
    "avgPlayTimeMs",
    "avgPlayDuration",
)
PROFILE_CLICK_KEYS = (
    "profile_click_count",
    "homepage_click",
    "click_user_count",
    "profile_uv",
    "clickProfileCount",
)


def first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def pick_from_maps(maps: list[Any], keys: tuple[str, ...]) -> Any:
    for mapping in maps:
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            if key not in mapping:
                continue
            value = mapping[key]
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
    return None


def extract_funnel_metric_fields(*maps: Any) -> dict[str, Any]:
    cleaned = [mapping for mapping in maps if isinstance(mapping, dict)]
    return {
        "follow_count": pick_from_maps(cleaned, FOLLOW_COUNT_KEYS),
        "play_3s_rate": pick_from_maps(cleaned, PLAY_3S_RATE_KEYS),
        "completion_rate": pick_from_maps(cleaned, COMPLETION_RATE_KEYS),
        "avg_watch_sec": pick_from_maps(cleaned, AVG_WATCH_KEYS),
        "profile_click_count": pick_from_maps(cleaned, PROFILE_CLICK_KEYS),
    }


def parse_rate_percent(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"—", "-", "暂无", "null", "None"}:
        return None
    is_percent_text = text.endswith("%")
    if is_percent_text:
        text = text[:-1].strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if number < 0:
        return None
    if not is_percent_text and 0 < number <= 1:
        number *= 100
    if number > 100:
        number = 100.0
    return round(number, 4)


def parse_duration_sec(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"—", "-", "暂无", "null", "None"}:
        return None
    lowered = text.lower()
    if lowered.endswith("ms"):
        try:
            return round(float(text[:-2].strip()) / 1000, 4)
        except ValueError:
            return None
    if lowered.endswith("s") and not lowered.endswith("ms"):
        text = text[:-1].strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if number < 0:
        return None
    if number >= 1000:
        return round(number / 1000, 4)
    return round(number, 4)


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 1_000_000_000_000:
                ts /= 1000
            return datetime.utcfromtimestamp(ts)
        except (OSError, ValueError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def build_post_metrics_items_from_rows(
    rows: list[dict[str, Any]],
    *,
    id_keys: tuple[str, ...] = ("platform_post_id", "note_id", "video_id", "photo_id", "export_id"),
    post_url_builder: Callable[[str], str | None] | None = None,
) -> list[PostMetricsItem]:
    items: list[PostMetricsItem] = []
    for row in rows:
        post_id = ""
        for key in id_keys:
            candidate = str(row.get(key) or "").strip()
            if candidate:
                post_id = candidate
                break
        if not post_id:
            continue
        post_url = row.get("post_url")
        if not post_url and post_url_builder is not None:
            post_url = post_url_builder(post_id)
        items.append(
            PostMetricsItem(
                platform_post_id=post_id,
                title=str(row.get("title") or ""),
                published_at=parse_datetime(row.get("published_at")),
                view_count=parse_count_text(
                    row.get("view_count") or row.get("read_count") or row.get("play_count")
                ),
                like_count=parse_count_text(row.get("like_count")),
                comment_count=parse_count_text(row.get("comment_count")),
                share_count=parse_count_text(row.get("share_count") or row.get("forward_count")),
                favorite_count=parse_count_text(
                    row.get("favorite_count") or row.get("collect_count")
                ),
                follow_count=parse_count_text(
                    first_present(
                        row.get("follow_count"),
                        row.get("followCount"),
                        row.get("fans_count"),
                    )
                ),
                play_3s_rate=parse_rate_percent(
                    first_present(row.get("play_3s_rate"), row.get("play3sRate"))
                ),
                completion_rate=parse_rate_percent(
                    first_present(row.get("completion_rate"), row.get("fullPlayRate"))
                ),
                avg_watch_sec=parse_duration_sec(
                    first_present(row.get("avg_watch_sec"), row.get("avgPlayTimeMs"))
                ),
                profile_click_count=parse_count_text(
                    first_present(
                        row.get("profile_click_count"),
                        row.get("homepage_click"),
                        row.get("clickProfileCount"),
                    )
                ),
                post_url=post_url,
                raw=dict(row),
            )
        )
    return items


def fetch_metrics_rows_with_session(
    session_path: Path,
    *,
    list_url: str,
    extract_js: str,
    platform_label: str,
    wait_ms: int = 3000,
    headless: bool = False,
    warmup_url: str | None = None,
    limit: int = 100,
    paginate: bool = False,
    needed_ids: set[str] | None = None,
    max_pages: int = 15,
) -> list[dict[str, Any]]:
    from services.publishing.browser_session import open_adapter_browser
    from services.publishing.human_interaction import human_idle_on_page
    from services.publishing.human_pacing import human_pause

    needed = {str(item).strip() for item in (needed_ids or set()) if item}

    with open_adapter_browser(session_path, mode="metrics", headless=headless) as sess:
        page = sess.page
        if warmup_url:
            page.goto(warmup_url, wait_until="domcontentloaded", timeout=60_000)
            human_pause(page, "page_load")
        page.goto(list_url, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        if not headless:
            human_idle_on_page(page, moves=1)
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        rows = list(page.evaluate(extract_js) or [])
        if paginate:
            seen = {metric_row_id(row) for row in rows if metric_row_id(row)}
            for _ in range(max(0, max_pages - 1)):
                if len(rows) >= limit and (not needed or needed.issubset(seen)):
                    break
                clicked = page.evaluate(_CLICK_NEXT_PAGE_JS)
                if not clicked:
                    page.evaluate("() => window.scrollBy(0, Math.max(800, window.innerHeight))")
                human_pause(page, "page_load")
                page.wait_for_timeout(1500)
                batch = page.evaluate(extract_js) or []
                added = 0
                for row in batch:
                    rid = metric_row_id(row)
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    rows.append(row)
                    added += 1
                if added == 0:
                    break
        logger.info("{} metrics fetched {} raw row(s)", platform_label, len(rows))
        return rows
