"""WeChat Channels creator first-comment automation."""
from __future__ import annotations

from typing import Any

import time

from loguru import logger

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.creator_comment_helpers import dismiss_overlays, wait_for_work
from services.publishing.human_form import human_fill
from services.publishing.human_interaction import human_click
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.wechat_channels import (
    _FETCH_POST_LIST_JS,
    parse_wechat_post_list_payload,
)
from services.publishing.metrics.post_id import is_synthetic_platform_post_id

if True:
    from playwright.sync_api import Locator, Page

COMMENT_HUB_URL = "https://channels.weixin.qq.com/platform/interaction/comment"

CLICK_FEED_BY_TITLE_JS = """
([titleNeedle, exportId, preferZeroComments]) => {
  const needle = String(titleNeedle || '').trim().toLowerCase();
  const compactNeedle = needle.replace(/\\s+/g, '');
  const normalizeExportId = (value) => {
    const text = String(value || '').trim();
    if (!text) return '';
    return text.replace(/^export\\//i, '');
  };
  const idNeedle = normalizeExportId(exportId);
  const idFull = String(exportId || '').trim();
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  const feedCount = (feed) => {
    const totalEl = feed.querySelector('.feed-comment-total');
    return parseInt((totalEl && totalEl.innerText) || '0', 10) || 0;
  };
  const feedExportId = (feed) => {
    const raw = feed.getAttribute('data-export-id') || feed.dataset?.exportId || '';
    return normalizeExportId(raw);
  };
  const feedMatchesId = (feed) => {
    if (!idNeedle && !idFull) return false;
    const fid = feedExportId(feed);
    if (fid && fid === idNeedle) return true;
    if (idFull && (feed.getAttribute('data-export-id') === idFull || feed.dataset?.exportId === idFull)) {
      return true;
    }
    const blob = `${feed.innerHTML || ''} ${feed.innerText || ''}`;
    if (idNeedle && blob.includes(idNeedle)) return true;
    return false;
  };
  const feedMatchesTitle = (feed) => {
    if (!needle && !compactNeedle) return false;
    const text = (feed.innerText || '').toLowerCase();
    const compactText = text.replace(/\\s+/g, '');
    return (needle && text.includes(needle)) || (compactNeedle && compactText.includes(compactNeedle));
  };
  const tryClick = (feed, mode) => {
    feed.click();
    return { clicked: true, mode, count: feedCount(feed) };
  };
  for (const root of roots) {
    const feeds = [...root.querySelectorAll('.comment-feed-wrap')];
    if (!feeds.length) continue;
    if (preferZeroComments) {
      const zeroFeeds = feeds.filter((feed) => feedCount(feed) === 0);
      const pool = zeroFeeds.length ? zeroFeeds : feeds;
      for (const feed of pool) {
        if (feedMatchesId(feed)) {
          return tryClick(feed, 'export_id');
        }
        if (feedMatchesTitle(feed)) {
          return tryClick(feed, 'title');
        }
      }
      if (!needle && !idNeedle) {
        return tryClick(pool[0], 'first');
      }
      continue;
    }
    for (const feed of feeds) {
      if (feedMatchesId(feed)) {
        return tryClick(feed, 'export_id');
      }
      if (feedMatchesTitle(feed)) {
        return tryClick(feed, 'title');
      }
    }
    if (!needle && !idNeedle) {
      return tryClick(feeds[0], 'first');
    }
  }
  return { clicked: false };
}
"""

SCROLL_COMMENT_FEED_LIST_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const selector of ['.comment-feed-list', '.comment-feeds', '[class*="feed-list"]', '[class*="feed-wrap"]']) {
      const list = root.querySelector(selector);
      if (list && list.scrollHeight > list.clientHeight + 20) {
        list.scrollTop += Math.max(240, Math.floor(list.clientHeight * 0.8));
        return { scrolled: true, mode: 'container' };
      }
    }
    const feeds = [...root.querySelectorAll('.comment-feed-wrap')];
    if (feeds.length) {
      feeds[feeds.length - 1].scrollIntoView({ block: 'end' });
      return { scrolled: true, mode: 'last_feed' };
    }
  }
  return { scrolled: false };
}
"""

CLICK_WRITE_COMMENT_TAB_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const el of root.querySelectorAll('.tag-wrap, .tag-inner, span, div, button')) {
      if ((el.innerText || '').trim() === '写评论') {
        el.click();
        return true;
      }
    }
  }
  return false;
}
"""

DISMISS_WECHAT_TIP_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const btn of root.querySelectorAll('button')) {
      const text = (btn.innerText || '').trim();
      if (text === '我知道了' || text.includes('知道了')) {
        btn.click();
        return true;
      }
    }
  }
  return false;
}
"""


def _fetch_work_rows(page: Page) -> list[dict[str, Any]]:
    payload = page.evaluate(_FETCH_POST_LIST_JS, [1, 20])
    if isinstance(payload, dict):
        rows = parse_wechat_post_list_payload(payload)
        if rows:
            return rows
    return []


def _navigate_comment_hub(page: Page, *, max_attempts: int = 3) -> None:
    if COMMENT_HUB_URL in (page.url or ""):
        dismiss_overlays(page)
        return

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            page.goto(COMMENT_HUB_URL, wait_until="domcontentloaded", timeout=60_000)
            human_pause(page, "page_load")
            dismiss_overlays(page)
            current_url = page.url or ""
            if "chromewebdata" not in current_url and "channels.weixin.qq.com" in current_url:
                return
            last_error = RuntimeError(f"unexpected_url:{current_url}")
        except Exception as exc:
            last_error = exc
            logger.warning(
                "评论中心导航失败 attempt={}/{} url={} err={}",
                attempt,
                max_attempts,
                page.url,
                exc,
            )
        if attempt < max_attempts:
            time.sleep(min(2 * attempt, 8))
            try:
                page.goto("about:blank", wait_until="domcontentloaded", timeout=15_000)
            except Exception:
                pass

    raise RuntimeError(f"comment_hub_navigate_failed:{last_error}")


def _wait_for_comment_feeds(page: Page, *, timeout_ms: int = 20_000) -> bool:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            if page.locator(".comment-feed-wrap").count() > 0:
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def _dismiss_wechat_tip(page: Page) -> None:
    for locator in (
        page.get_by_role("button", name="我知道了"),
        page.locator('button:has-text("我知道了")'),
    ):
        try:
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                locator.first.click(timeout=2000)
                human_pause(page, "after_click")
                return
        except Exception:
            continue
    page.evaluate(DISMISS_WECHAT_TIP_JS)


def _select_feed(page: Page, work: dict[str, Any]) -> bool:
    if not _wait_for_comment_feeds(page):
        return False
    title = str(work.get("title") or "").strip()
    export_id = str(work.get("export_id") or "").strip()
    needle = title[:24] if title else ""
    clicked = page.evaluate(CLICK_FEED_BY_TITLE_JS, [needle, export_id, True])
    if not (isinstance(clicked, dict) and clicked.get("clicked")):
        clicked = page.evaluate(CLICK_FEED_BY_TITLE_JS, ["", "", True])
    human_pause(page, "page_load")
    return bool(isinstance(clicked, dict) and clicked.get("clicked"))


def _open_write_comment_tab(page: Page) -> bool:
    opened = page.evaluate(CLICK_WRITE_COMMENT_TAB_JS)
    human_pause(page, "after_click")
    return bool(opened)


def _find_wechat_comment_input(page: Page) -> Locator | None:
    for selector in (
        'textarea.create-input[placeholder*="发表"]',
        'textarea.create-input',
        'textarea[placeholder*="发表"]',
    ):
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=1500):
                return loc.first
        except Exception:
            continue
    return None


CLICK_WECHAT_SUBMIT_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  const tryRoot = (root) => {
    for (const scope of root.querySelectorAll('.comment-create-wrap, .reply-to-feed')) {
      for (const el of scope.querySelectorAll('.tag-wrap.primary .tag-inner, button')) {
        const text = (el.innerText || '').trim();
        if (text !== '发表') continue;
        const disabled = el.closest('.tag-wrap')?.classList?.contains('disabled');
        if (disabled) continue;
        el.click();
        return true;
      }
      for (const btn of scope.querySelectorAll('button.weui-desktop-btn_primary')) {
        const text = (btn.innerText || '').trim();
        if (text === '发表' && !btn.disabled) {
          btn.click();
          return true;
        }
      }
    }
    return false;
  };
  for (const root of roots) {
    if (tryRoot(root)) return true;
  }
  return false;
}
"""


def _find_wechat_submit_button(page: Page) -> Locator | None:
    for locator in (
        page.locator('.comment-create-wrap .tag-wrap.primary .tag-inner'),
        page.locator('.comment-create-wrap .create-ft .tag-wrap.primary'),
        page.locator('.reply-to-feed .tag-wrap.primary .tag-inner'),
        page.get_by_role("button", name="发表"),
        page.locator('.comment-create-wrap button.weui-desktop-btn_primary:has-text("发表")'),
        page.locator('button.weui-desktop-btn_primary:has-text("发表")'),
    ):
        try:
            if locator.count() > 0 and locator.first.is_visible(timeout=800):
                text = (locator.first.inner_text(timeout=500) or "").strip()
                if text in {"切换", "我知道了", "取消"}:
                    continue
                if text == "发表" or "tag-wrap" in str(locator):
                    return locator.first
        except Exception:
            continue
    return None


def _prepare_wechat_comment_surface(page: Page, work: dict[str, Any]) -> CommentResult | None:
    _navigate_comment_hub(page)
    page.wait_for_timeout(3000)
    if not _select_feed(page, work):
        return CommentResult(success=False, error_message="work_not_found")
    page.wait_for_timeout(2500)
    if not _open_write_comment_tab(page):
        return CommentResult(success=False, error_message="write_comment_tab_not_found")
    page.wait_for_timeout(1500)
    _dismiss_wechat_tip(page)
    human_pause(page, "after_click")
    if _find_wechat_comment_input(page) is None:
        return CommentResult(success=False, error_message="comment_input_not_found")
    return None


def _fill_and_submit_wechat_comment(page: Page, text: str) -> CommentResult:
    comment_input = _find_wechat_comment_input(page)
    if comment_input is None:
        return CommentResult(success=False, error_message="comment_input_not_found")

    try:
        human_fill(page, comment_input, text)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"fill_failed:{exc}")

    _dismiss_wechat_tip(page)
    human_pause(page, "after_type")

    submit = _find_wechat_submit_button(page)
    if submit is not None:
        try:
            human_click(page, submit, timeout_ms=8000)
            human_pause(page, "after_click")
        except Exception as exc:
            return CommentResult(success=False, error_message=f"submit_click_failed:{exc}")
    elif not page.evaluate(CLICK_WECHAT_SUBMIT_JS):
        return CommentResult(success=False, error_message="submit_button_not_found")
    else:
        human_pause(page, "after_click")

    logger.info("视频号首评已提交")
    return CommentResult(success=True)


def post_wechat_first_comment(
    page: Page,
    *,
    text: str,
    title: str,
    export_id: str | None = None,
    delay_sec: int = 15,
    wait_max_sec: int = 60,
    dry_run: bool = False,
) -> CommentResult:
    cleaned = (text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_comment_text")

    real_id = None if is_synthetic_platform_post_id(export_id) else export_id
    work = {"export_id": real_id, "title": title}

    if real_id or title.strip():
        prep_error = _prepare_wechat_comment_surface(page, work)
        if prep_error is None:
            if dry_run:
                return CommentResult(success=True)
            return _fill_and_submit_wechat_comment(page, cleaned)
        if prep_error.error_message != "work_not_found":
            return prep_error

    polled = wait_for_work(
        page,
        list_url=COMMENT_HUB_URL,
        fetch_rows=_fetch_work_rows,
        title=title,
        post_id=real_id,
        delay_sec=delay_sec if not real_id else 0,
        wait_max_sec=wait_max_sec,
        id_keys=("export_id",),
    )
    if polled is None:
        return CommentResult(success=False, error_message="work_not_found")

    prep_error = _prepare_wechat_comment_surface(page, polled)
    if prep_error is not None:
        return prep_error
    if dry_run:
        return CommentResult(success=True)
    return _fill_and_submit_wechat_comment(page, cleaned)
