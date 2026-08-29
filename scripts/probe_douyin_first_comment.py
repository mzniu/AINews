"""Probe Douyin creator first-comment flow (Spike gate for post-publish auto comment).

Usage:
  python scripts/probe_douyin_first_comment.py
  python scripts/probe_douyin_first_comment.py --title "关键词"
  python scripts/probe_douyin_first_comment.py --video-id 7123456789
  python scripts/probe_douyin_first_comment.py --post --comment "你觉得这个数靠谱吗？"

PASS (dry-run): work_list 能取到作品 + 能进入详情/互动页 + 定位到评论输入框
PASS (--post):  上述 + 评论提交成功（或页面可见新评论）

Reports: data/publish/probe_douyin_first_comment_report.json
Screenshots: data/publish/screenshots/probe_first_comment_*.png
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import Page, sync_playwright

from services.publishing.human_form import human_fill
from services.publishing.human_interaction import (
    create_publish_browser_context,
    human_click,
    launch_publish_browser,
)
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.douyin import (
    CONTENT_MANAGE_URL,
    CREATOR_HOME_URL,
    DEFAULT_WORK_LIST_QUERY,
    _FETCH_WORK_LIST_JS,
    _page_requires_login,
    parse_douyin_work_list_payload,
)
from services.publishing.metrics.post_id import build_douyin_post_url
from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

REPORT_PATH = Config.ROOT_DIR / "data" / "publish" / "probe_douyin_first_comment_report.json"
SCREENSHOT_DIR = Config.ROOT_DIR / "data" / "publish" / "screenshots"

COMMENT_INPUT_SELECTORS = (
    'textarea[placeholder*="评论"]',
    'textarea[placeholder*="说点什么"]',
    'textarea[placeholder*="友善"]',
    'textarea[placeholder*="留下"]',
    'input[placeholder*="评论"]',
    'input[placeholder*="留下"]',
    'div[contenteditable="true"][data-placeholder*="评论"]',
    'div[contenteditable="true"][data-placeholder*="说"]',
    'div[contenteditable="true"][data-placeholder*="留下"]',
    '[aria-label*="评论"]',
    '[placeholder*="留下你的精彩评论"]',
    '[placeholder*="留下精彩评论"]',
    'div.public-DraftEditor-content',
    '[class*="comment"] [contenteditable="true"]',
    '[data-e2e="comment-input"] [contenteditable="true"]',
    '[contenteditable="true"]',
)

COMMENT_MANAGE_URLS = (
    "https://creator.douyin.com/creator-micro/interactive/comment?item_id={video_id}",
    "https://creator.douyin.com/creator-micro/interactive/comment?aweme_id={video_id}",
    "https://creator.douyin.com/creator-micro/interactive/comment",
    "https://creator.douyin.com/creator-micro/interactive/comment/list",
    "https://creator.douyin.com/creator-micro/data/following/comment",
    "https://creator.douyin.com/creator-micro/interactive/interactivemanage?type=comment",
)

COMMENT_SUBMIT_SELECTORS = (
    'button:has-text("发送")',
    'button:has-text("发布")',
    'span:has-text("发送")',
    '[class*="comment"] button:has-text("发送")',
    '[class*="send"]',
)

DETAIL_URL_TEMPLATES = (
    "https://creator.douyin.com/creator-micro/content/manage/detail?item_id={video_id}",
    "https://creator.douyin.com/creator-micro/content/detail?item_id={video_id}",
    "https://creator.douyin.com/creator-micro/content/detail?enter_from=publish&item_id={video_id}",
)

_PROBE_COMMENT_INPUTS_JS = """() => {
  const out = [];
  const nodes = document.querySelectorAll(
    'textarea, input[type="text"], [contenteditable="true"]'
  );
  for (const el of nodes) {
    const placeholder = el.getAttribute('placeholder')
      || el.getAttribute('data-placeholder')
      || el.getAttribute('aria-placeholder')
      || '';
    const aria = el.getAttribute('aria-label') || '';
    const hint = `${placeholder} ${aria}`.toLowerCase();
    const rect = el.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 16) continue;
    const visible = rect.bottom > 0 && rect.right > 0
      && rect.top < (window.innerHeight || 0)
      && rect.left < (window.innerWidth || 0);
    if (!visible) continue;
    out.push({
      tag: el.tagName,
      placeholder,
      aria,
      className: String(el.className || '').slice(0, 120),
      hint,
      looks_like_comment: /评论|comment|说点|友善|互动/.test(hint),
    });
  }
  return out;
}"""

_PROBE_CLICK_COMMENT_AREA_JS = """() => {
  const labels = ['留下你的精彩评论', '留下精彩评论', '说点什么', '友善评论', '发表评论'];
  for (const el of document.querySelectorAll(
    'textarea, input, [contenteditable="true"], [contenteditable=""]'
  )) {
    const ph = el.getAttribute('placeholder')
      || el.getAttribute('data-placeholder')
      || el.getAttribute('aria-placeholder')
      || '';
    if (labels.some((label) => ph.includes(label))) {
      el.scrollIntoView({ block: 'center' });
      el.click();
      return { clicked: true, kind: 'input', placeholder: ph };
    }
  }
  const tabs = [...document.querySelectorAll('span, div, button, a')].filter((el) => {
    const text = (el.innerText || '').trim();
    return text === '评论' && el.children.length === 0;
  });
  for (const tab of tabs) {
    const rect = tab.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) continue;
    tab.scrollIntoView({ block: 'center' });
    tab.click();
    return { clicked: true, kind: 'tab' };
  }
  return { clicked: false };
}"""


_PROBE_MANAGE_LINKS_JS = """() => {
  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('a[href], [role="row"], tr, [class*="item"]')) {
    const href = el.getAttribute('href') || '';
    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 100);
    const key = `${href}|${text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (!href && text.length < 4) continue;
    out.push({
      tag: el.tagName,
      href,
      text,
      className: String(el.className || '').slice(0, 80),
    });
    if (out.length >= 40) break;
  }
  return out;
}"""


def _load_account(account_id: str | None) -> PublisherAccount | None:
    init_db()
    factory = get_session_factory()
    with factory() as session:
        query = session.query(PublisherAccount).filter(PublisherAccount.platform == "douyin")
        if account_id:
            query = query.filter(PublisherAccount.id == account_id)
        else:
            query = query.filter(PublisherAccount.status == "active")
        return query.order_by(PublisherAccount.last_login_at.desc().nullslast()).first()


def _fetch_work_rows(page: Page) -> list[dict[str, Any]]:
    payload = page.evaluate(_FETCH_WORK_LIST_JS, dict(DEFAULT_WORK_LIST_QUERY))
    if not isinstance(payload, dict):
        return []
    return parse_douyin_work_list_payload(payload)


def _pick_work(
    rows: list[dict[str, Any]],
    *,
    title: str | None,
    video_id: str | None,
) -> dict[str, Any] | None:
    if video_id:
        for row in rows:
            if str(row.get("video_id") or "") == str(video_id):
                return row
    if title:
        needle = title.strip().lower()
        for row in rows:
            hay = str(row.get("title") or "").lower()
            if needle in hay:
                return row
    return rows[0] if rows else None


def _screenshot(page: Page, name: str) -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"probe_first_comment_{name}_{int(time.time())}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        pass
    return str(path)


def _page_has_comment_hint(page: Page) -> bool:
    text = page.evaluate("() => (document.body.innerText || '').slice(0, 4000)") or ""
    return any(token in text for token in ("评论", "互动", "comment", "说点什么", "友善评论"))


def _input_hint_excluded(hint: str) -> bool:
    lowered = (hint or "").lower()
    return any(token in lowered for token in ("搜索", "作品", "search", "关键词", "标题", "描述"))


def _find_comment_locator(page: Page):
    from playwright.sync_api import Locator

    page_url = page.url or ""
    on_public_video = "www.douyin.com/video/" in page_url
    ranked: list[tuple[int, Locator]] = []
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
            hint = ""
            try:
                hint = item.evaluate(
                    """(el) => {
                      return [
                        el.getAttribute('placeholder'),
                        el.getAttribute('data-placeholder'),
                        el.getAttribute('aria-label'),
                      ].filter(Boolean).join(' ');
                    }"""
                )
            except Exception:
                pass
            if _input_hint_excluded(hint):
                continue
            score = 0
            if any(token in (hint or "") for token in ("评论", "说点", "友善", "留下")):
                score += 10
            if on_public_video and "contenteditable" in selector:
                score += 5
            if score <= 0:
                continue
            ranked.append((score, item))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def _find_submit_locator(page: Page):
    for selector in COMMENT_SUBMIT_SELECTORS:
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=800):
                return loc.first
        except Exception:
            continue
    return None


def _dismiss_overlays(page: Page) -> None:
    for text in ("跳过", "我知道了", "关闭", "下次再说", "不再提示"):
        try:
            btn = page.get_by_text(text, exact=False)
            if btn.count() > 0 and btn.first.is_visible(timeout=400):
                btn.first.click(timeout=2000)
                human_pause(page, "after_click")
        except Exception:
            continue
    for selector in (
        '[aria-label="关闭"]',
        '[class*="close"]',
        'button[class*="close"]',
    ):
        try:
            loc = page.locator(selector)
            if loc.count() > 0 and loc.first.is_visible(timeout=400):
                loc.first.click(timeout=2000)
                human_pause(page, "after_click")
                break
        except Exception:
            continue


def _is_wrong_navigation_url(url: str, video_id: str) -> bool:
    normalized = (url or "").rstrip("/")
    if normalized.endswith("/creator-micro/home"):
        return True
    if "/creator-micro/home" in url and "item_id" not in url and video_id not in url:
        return True
    if normalized.endswith("/creator-micro/content/manage") and video_id not in url:
        return False
    return False


def _comment_surface_ready(page: Page) -> bool:
    return _find_comment_locator(page) is not None


def _click_comment_tabs(page: Page) -> None:
    for tab_text in ("评论管理", "评论", "互动", "互动数据"):
        try:
            tabs = page.get_by_role("tab", name=tab_text)
            if tabs.count() > 0 and tabs.first.is_visible(timeout=800):
                tabs.first.click(timeout=3000)
                human_pause(page, "after_click")
                return
            loc = page.get_by_text(tab_text, exact=True)
            if loc.count() > 0 and loc.first.is_visible(timeout=800):
                loc.first.click(timeout=3000)
                human_pause(page, "after_click")
                return
        except Exception:
            continue


def _locate_work_row(page: Page, work: dict[str, Any]):
    title_short = str(work.get("title") or "").strip()[:20]
    if not title_short:
        return None
    for selector in (
        f'[class*="content"]:has-text("{title_short}")',
        f'[class*="video"]:has-text("{title_short}")',
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


def _drill_work_row_for_comments(
    page: Page,
    work: dict[str, Any],
    report: dict[str, Any],
    prefix: str,
) -> str | None:
    row = _locate_work_row(page, work)
    if row is None:
        _record_nav_attempt(
            report,
            method=f"{prefix}_row",
            url=page.url,
            ready=False,
            note="row_not_found",
        )
        return None

    comment_count = work.get("comment_count")
    if comment_count is not None:
        count_str = str(comment_count)
        try:
            stat = row.get_by_text(count_str, exact=True)
            if stat.count() > 0 and stat.first.is_visible(timeout=1200):
                stat.first.click(timeout=4000)
                human_pause(page, "after_click")
                _click_comment_tabs(page)
                if _comment_surface_ready(page):
                    _record_nav_attempt(
                        report,
                        method=f"{prefix}_comment_stat",
                        url=page.url,
                        ready=True,
                    )
                    return f"{prefix}_comment_stat"
        except Exception as exc:
            _record_nav_attempt(
                report,
                method=f"{prefix}_comment_stat",
                url=page.url,
                ready=False,
                note=str(exc),
            )

    for img_sel in ("img", '[class*="cover"]', '[class*="thumb"]', '[class*="poster"]'):
        try:
            img = row.locator(img_sel).first
            if img.count() > 0 and img.is_visible(timeout=800):
                img.click(timeout=4000)
                human_pause(page, "after_click")
                _click_comment_tabs(page)
                if _comment_surface_ready(page):
                    _record_nav_attempt(
                        report,
                        method=f"{prefix}_thumb",
                        url=page.url,
                        ready=True,
                    )
                    return f"{prefix}_thumb"
        except Exception:
            continue

    title_short = str(work.get("title") or "").strip()[:20]
    try:
        title_loc = row.get_by_text(title_short, exact=False).first
        if title_loc.count() > 0 and title_loc.is_visible(timeout=1500):
            title_loc.click(timeout=5000)
            human_pause(page, "page_load")
            _click_comment_tabs(page)
            if _comment_surface_ready(page):
                _record_nav_attempt(
                    report,
                    method=f"{prefix}_title",
                    url=page.url,
                    ready=True,
                )
                return f"{prefix}_title"
    except Exception as exc:
        _record_nav_attempt(
            report,
            method=f"{prefix}_title",
            url=page.url,
            ready=False,
            note=str(exc),
        )

    return None


def _record_nav_attempt(
    report: dict[str, Any],
    *,
    method: str,
    url: str,
    ready: bool,
    note: str = "",
) -> None:
    nav = report.setdefault("navigation", {"attempts": []})
    nav["attempts"].append(
        {
            "method": method,
            "url": url,
            "ready": ready,
            "note": note,
        }
    )


def _scroll_to_comment_section(page: Page) -> None:
    for _ in range(4):
        try:
            page.evaluate("() => window.scrollBy(0, Math.max(400, window.innerHeight * 0.8))")
        except Exception:
            pass
        human_pause(page, "step")
    for selector in (
        '[data-e2e="comment-tab"]',
        '[data-e2e="feed-comment-icon"]',
        'span:has-text("评论")',
        'div:has-text("评论")',
    ):
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible(timeout=800):
                loc.click(timeout=3000)
                human_pause(page, "after_click")
                break
        except Exception:
            continue


def _try_public_video_page(
    page: Page,
    video_id: str,
    report: dict[str, Any],
) -> str | None:
    if not video_id:
        return None
    url = build_douyin_post_url(video_id)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        human_pause(page, "page_load")
        _dismiss_overlays(page)
        if "login" in page.url.lower():
            _record_nav_attempt(
                report,
                method="public_video",
                url=page.url,
                ready=False,
                note="login_wall",
            )
            return None
        click_result = page.evaluate(_PROBE_CLICK_COMMENT_AREA_JS)
        report.setdefault("public_video_probe", {})["click_result"] = click_result
        human_pause(page, "after_click")
        _scroll_to_comment_section(page)
        page.evaluate(_PROBE_CLICK_COMMENT_AREA_JS)
        human_pause(page, "step")
        ready = _comment_surface_ready(page)
        _record_nav_attempt(report, method="public_video", url=page.url, ready=ready)
        if ready:
            return "public_video"
    except Exception as exc:
        _record_nav_attempt(
            report,
            method="public_video",
            url=url,
            ready=False,
            note=str(exc),
        )
    return None


def _try_manage_row_drill(
    page: Page,
    work: dict[str, Any],
    report: dict[str, Any],
) -> str | None:
    try:
        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        _dismiss_overlays(page)
        drilled = _drill_work_row_for_comments(page, work, report, "manage_row")
        if drilled:
            return drilled
    except Exception as exc:
        _record_nav_attempt(
            report,
            method="manage_row_drill",
            url=page.url,
            ready=False,
            note=str(exc),
        )
    return None


def _try_open_detail_urls(
    page: Page,
    video_id: str,
    work: dict[str, Any],
    report: dict[str, Any],
) -> str | None:
    for template in DETAIL_URL_TEMPLATES:
        url = template.format(video_id=video_id)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            human_pause(page, "page_load")
            _dismiss_overlays(page)
            drilled = _drill_work_row_for_comments(page, work, report, "detail_drill")
            if drilled:
                return drilled
            ready = _comment_surface_ready(page)
            _record_nav_attempt(report, method=f"detail_url:{template}", url=page.url, ready=ready)
            if ready and not _is_wrong_navigation_url(page.url, video_id):
                return f"detail_url:{template}"
        except Exception as exc:
            _record_nav_attempt(
                report,
                method=f"detail_url:{template}",
                url=url,
                ready=False,
                note=str(exc),
            )
            continue
    return None


def _try_comment_manage_flow(
    page: Page,
    work: dict[str, Any],
    report: dict[str, Any],
) -> str | None:
    title = str(work.get("title") or "").strip()
    video_id = str(work.get("video_id") or "").strip()
    title_short = title[:18].strip() if title else ""

    for manage_template in COMMENT_MANAGE_URLS:
        manage_url = manage_template.format(video_id=video_id) if "{video_id}" in manage_template else manage_template
        try:
            page.goto(manage_url, wait_until="domcontentloaded", timeout=45_000)
            human_pause(page, "page_load")
            _dismiss_overlays(page)

            for pick_text in ("选择视频", "切换作品", "选择作品"):
                try:
                    pick_btn = page.get_by_text(pick_text, exact=False)
                    if pick_btn.count() > 0 and pick_btn.first.is_visible(timeout=1000):
                        pick_btn.first.click(timeout=4000)
                        human_pause(page, "after_click")
                        break
                except Exception:
                    continue

            if title_short:
                try:
                    title_loc = page.get_by_text(title_short, exact=False).first
                    if title_loc.count() > 0 and title_loc.is_visible(timeout=2000):
                        title_loc.click(timeout=5000)
                        human_pause(page, "after_click")
                except Exception:
                    pass

            if video_id:
                try:
                    href_loc = page.locator(f'a[href*="{video_id}"]').first
                    if href_loc.count() > 0 and href_loc.is_visible(timeout=1500):
                        href_loc.click(timeout=5000)
                        human_pause(page, "after_click")
                except Exception:
                    pass

            ready = _comment_surface_ready(page)
            _record_nav_attempt(
                report,
                method=f"comment_manage:{manage_url}",
                url=page.url,
                ready=ready,
            )
            if ready:
                return f"comment_manage:{manage_url}"
        except Exception as exc:
            _record_nav_attempt(
                report,
                method=f"comment_manage:{manage_url}",
                url=manage_url,
                ready=False,
                note=str(exc),
            )
    return None


def _try_open_from_manage(
    page: Page,
    work: dict[str, Any],
    report: dict[str, Any],
) -> str | None:
    page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    human_pause(page, "page_load")
    _dismiss_overlays(page)
    human_pause(page, "page_load")

    title = str(work.get("title") or "").strip()
    video_id = str(work.get("video_id") or "").strip()
    title_short = title[:18].strip() if title else ""

    drilled = _drill_work_row_for_comments(page, work, report, "manage_click")
    if drilled:
        return drilled

    # Prefer links that contain the video id — never click generic list items.
    if video_id:
        try:
            href_loc = page.locator(f'a[href*="{video_id}"]').first
            if href_loc.count() > 0 and href_loc.is_visible(timeout=2500):
                href_loc.click(timeout=5000)
                human_pause(page, "after_click")
                ready = _comment_surface_ready(page)
                _record_nav_attempt(report, method="manage_click_href", url=page.url, ready=ready)
                if ready and not _is_wrong_navigation_url(page.url, video_id):
                    return "manage_click_href"
        except Exception as exc:
            _record_nav_attempt(
                report,
                method="manage_click_href",
                url=page.url,
                ready=False,
                note=str(exc),
            )

    if title_short:
        try:
            scoped = page.locator(
                'main, [class*="content-manage"], [class*="video-list"], table tbody'
            ).first
            title_loc = scoped.get_by_text(title_short, exact=False).first
            if title_loc.count() > 0 and title_loc.is_visible(timeout=2000):
                title_loc.click(timeout=5000)
                human_pause(page, "after_click")
                ready = _comment_surface_ready(page)
                _record_nav_attempt(report, method="manage_click_title", url=page.url, ready=ready)
                if ready and not _is_wrong_navigation_url(page.url, video_id):
                    return "manage_click_title"
        except Exception as exc:
            _record_nav_attempt(
                report,
                method="manage_click_title",
                url=page.url,
                ready=False,
                note=str(exc),
            )

    _record_nav_attempt(
        report,
        method="manage_page",
        url=page.url,
        ready=False,
        note="no_specific_row_click",
    )
    return None


def _navigate_to_comment_surface(
    page: Page,
    work: dict[str, Any],
    report: dict[str, Any],
) -> str | None:
    video_id = str(work.get("video_id") or "").strip()
    report["navigation"] = {"attempts": []}

    for strategy in (
        lambda: _try_manage_row_drill(page, work, report),
        lambda: _try_public_video_page(page, video_id, report),
        lambda: _try_open_detail_urls(page, video_id, work, report) if video_id else None,
        lambda: _try_comment_manage_flow(page, work, report),
        lambda: _try_open_from_manage(page, work, report),
    ):
        method = strategy()
        if method:
            report["navigation"]["method"] = method
            report["navigation"]["url"] = page.url
            return method

    report["navigation"]["url"] = page.url
    return None


def _poll_for_work(
    page: Page,
    *,
    title: str | None,
    video_id: str | None,
    delay_sec: int,
    wait_max_sec: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    deadline = time.time() + wait_max_sec
    if delay_sec > 0:
        time.sleep(delay_sec)
    last_rows: list[dict[str, Any]] = []
    while time.time() <= deadline:
        last_rows = _fetch_work_rows(page)
        work = _pick_work(last_rows, title=title, video_id=video_id)
        if work is not None:
            return work, last_rows
        human_pause(page, "polling")
        time.sleep(5)
    return None, last_rows


def run_probe(
    *,
    account_id: str | None,
    title: str | None,
    video_id: str | None,
    delay_sec: int,
    wait_max_sec: int,
    comment_text: str,
    post: bool,
    headless: bool,
) -> dict[str, Any]:
    started = time.time()
    report: dict[str, Any] = {
        "started_at": datetime.utcnow().isoformat(),
        "account_id": account_id,
        "title_filter": title,
        "video_id_filter": video_id,
        "delay_sec": delay_sec,
        "wait_max_sec": wait_max_sec,
        "post": post,
        "success": False,
        "gate": "FAIL",
        "screenshots": [],
        "errors": [],
    }

    account = _load_account(account_id)
    if account is None:
        report["errors"].append("no_active_douyin_account")
        return report

    report["account_id"] = account.id
    session_path = Config.ROOT_DIR / account.session_path
    if not session_path.exists():
        report["errors"].append(f"session_missing:{session_path}")
        return report

    temp_state = Config.ROOT_DIR / "data" / "publish" / "_probe_first_comment_state.json"
    temp_state.write_bytes(load_encrypted(session_path))

    playwright = sync_playwright().start()
    browser = launch_publish_browser(playwright, headless=headless)
    context = create_publish_browser_context(browser, storage_state=str(temp_state))
    page = context.new_page()

    try:
        page.goto(CREATOR_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")

        if _page_requires_login(page.evaluate("() => document.body.innerText || ''")):
            report["errors"].append("session_expired")
            report["screenshots"].append(_screenshot(page, "login_required"))
            return report

        work, rows = _poll_for_work(
            page,
            title=title,
            video_id=video_id,
            delay_sec=delay_sec,
            wait_max_sec=wait_max_sec,
        )
        report["work_list_count"] = len(rows)
        report["work_list_sample"] = rows[:3]

        if work is None:
            report["errors"].append("work_not_found")
            report["screenshots"].append(_screenshot(page, "no_work"))
            return report

        report["work"] = work
        report["navigation"] = {"attempts": []}

        nav_method = _navigate_to_comment_surface(page, work, report)
        if not nav_method:
            report["errors"].append("navigation_failed")
            report["navigation"]["manage_links"] = page.evaluate(_PROBE_MANAGE_LINKS_JS)
            report["screenshots"].append(_screenshot(page, "navigation_failed"))
            return report

        report["screenshots"].append(_screenshot(page, "detail_page"))
        report["comment_candidates"] = page.evaluate(_PROBE_COMMENT_INPUTS_JS)
        report["page_has_comment_hint"] = _page_has_comment_hint(page)

        comment_loc = _find_comment_locator(page)
        if comment_loc is None:
            report["errors"].append("comment_input_not_found")
            report["screenshots"].append(_screenshot(page, "no_comment_input"))
            return report

        report["comment_input_found"] = True
        selector_desc = comment_loc.evaluate(
            """(el) => ({
              tag: el.tagName,
              placeholder: el.getAttribute('placeholder') || el.getAttribute('data-placeholder') || '',
              aria: el.getAttribute('aria-label') || '',
              className: String(el.className || '').slice(0, 120),
            })"""
        )
        report["comment_input"] = selector_desc

        if not post:
            report["success"] = True
            report["gate"] = "PASS_DRY_RUN"
            return report

        try:
            human_fill(page, comment_loc, comment_text)
        except Exception as exc:
            report["errors"].append(f"fill_failed:{exc}")
            report["screenshots"].append(_screenshot(page, "fill_failed"))
            return report

        submit_loc = _find_submit_locator(page)
        if submit_loc is None:
            report["errors"].append("submit_button_not_found")
            report["screenshots"].append(_screenshot(page, "no_submit"))
            return report

        try:
            human_click(page, submit_loc, timeout_ms=8000)
            human_pause(page, "after_click")
        except Exception as exc:
            report["errors"].append(f"submit_click_failed:{exc}")
            report["screenshots"].append(_screenshot(page, "submit_failed"))
            return report

        report["screenshots"].append(_screenshot(page, "after_submit"))
        body_text = page.evaluate("() => document.body.innerText || ''") or ""
        report["comment_visible_in_page"] = comment_text[:20] in body_text
        report["posted"] = True
        report["success"] = True
        report["gate"] = "PASS_POST"
        return report
    finally:
        report["elapsed_sec"] = round(time.time() - started, 2)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written: {REPORT_PATH}")
        print(json.dumps(
            {
                "gate": report.get("gate"),
                "success": report.get("success"),
                "work": report.get("work"),
                "navigation": report.get("navigation"),
                "comment_input": report.get("comment_input"),
                "errors": report.get("errors"),
                "elapsed_sec": report.get("elapsed_sec"),
            },
            ensure_ascii=False,
            indent=2,
        ))
        browser.close()
        playwright.stop()
        temp_state.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Douyin first-comment spike")
    parser.add_argument("--account-id", help="Douyin PublisherAccount id (default: first active)")
    parser.add_argument("--title", help="Match work title substring")
    parser.add_argument("--video-id", help="Match aweme/video id")
    parser.add_argument("--delay-sec", type=int, default=0, help="Wait before polling work_list")
    parser.add_argument("--wait-max-sec", type=int, default=60, help="Max seconds to poll work_list")
    parser.add_argument(
        "--comment",
        default="【Spike】你觉得这条资讯最关键的点是什么？",
        help="Comment text when --post",
    )
    parser.add_argument("--post", action="store_true", help="Actually submit comment (default: dry-run)")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    args = parser.parse_args()

    report = run_probe(
        account_id=args.account_id,
        title=args.title,
        video_id=args.video_id,
        delay_sec=args.delay_sec,
        wait_max_sec=args.wait_max_sec,
        comment_text=args.comment,
        post=args.post,
        headless=args.headless,
    )
    if report.get("gate", "").startswith("PASS"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
