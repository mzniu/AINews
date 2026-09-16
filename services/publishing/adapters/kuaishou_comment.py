"""Kuaishou creator first-comment automation."""
from __future__ import annotations

from typing import Any

from loguru import logger

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.creator_comment_helpers import (
    dismiss_overlays,
    pick_work,
    wait_for_work,
)
from services.publishing.human_form import human_fill
from services.publishing.human_interaction import human_click
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.kuaishou import (
    CONTENT_MANAGE_URL,
    PHOTO_LIST_PATH,
    _EXTRACT_ROWS_JS,
    _FETCH_PHOTO_LIST_JS,
    parse_kuaishou_photo_list_payload,
)
from services.publishing.metrics.post_id import is_synthetic_platform_post_id

if True:
    from playwright.sync_api import Locator, Page

COMMENT_HUB_URL = "https://cp.kuaishou.com/article/comment"

# Content-manage first-comment flow: may include `.video-info` rows.
CLICK_VIDEO_BY_TITLE_JS = """
([titleNeedle, photoId]) => {
  const needle = String(titleNeedle || '').trim().toLowerCase();
  const idNeedle = String(photoId || '').trim();
  const feeds = [...document.querySelectorAll('.comment-home-video, .video-info')];
  for (const feed of feeds) {
    const text = (feed.innerText || '').toLowerCase();
    if (idNeedle && text.includes(idNeedle)) {
      feed.click();
      return { clicked: true, mode: 'photo_id' };
    }
    if (needle && text.includes(needle)) {
      feed.click();
      return { clicked: true, mode: 'title' };
    }
  }
  const first = document.querySelector('.comment-home-video');
  if (first) {
    first.click();
    return { clicked: true, mode: 'first' };
  }
  return { clicked: false };
}
"""

# Audience reply on comment hub only — never click `.video-info` (opens new tabs).
CLICK_COMMENT_HUB_VIDEO_JS = """
([titleNeedle, photoId]) => {
  const needle = String(titleNeedle || '').trim().toLowerCase();
  const idNeedle = String(photoId || '').trim();
  const feeds = [...document.querySelectorAll('.comment-home-video')];
  const activate = (feed) => {
    for (const link of feed.querySelectorAll('a[href]')) {
      link.removeAttribute('target');
      link.removeAttribute('rel');
      link.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
      }, { capture: true, once: true });
    }
    const target = feed.querySelector('[role="button"], button, .video-item, .video-card') || feed;
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    return true;
  };
  for (const feed of feeds) {
    const text = (feed.innerText || '').toLowerCase();
    const pid = feed.getAttribute('data-photo-id') || feed.dataset?.photoId || '';
    if (idNeedle && (pid === idNeedle || text.includes(idNeedle))) {
      activate(feed);
      return { clicked: true, mode: 'photo_id' };
    }
    if (needle && text.includes(needle)) {
      activate(feed);
      return { clicked: true, mode: 'title' };
    }
  }
  if (!idNeedle && !needle && feeds[0]) {
    activate(feeds[0]);
    return { clicked: true, mode: 'first' };
  }
  return { clicked: false };
}
"""

KUAISHOU_POPUP_BLOCKER_JS = """
() => {
  if (window.__ainewsKsPopupBlocker) return;
  window.__ainewsKsPopupBlocker = true;
  window.open = function(url) {
    try {
      if (url && String(url) !== 'about:blank') {
        window.location.assign(String(url));
      }
    } catch (e) {}
    return window;
  };
  document.addEventListener('click', (event) => {
    const link = event.target && event.target.closest
      ? event.target.closest('a[target="_blank"], a[target="blank"]')
      : null;
    if (!link) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const href = link.getAttribute('href');
    if (!href || href === '#') return;
    link.removeAttribute('target');
    link.removeAttribute('rel');
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
  }, true);
}
"""

EXTRACT_COMMENT_HUB_ROWS_JS = """
() => {
  const rows = [];
  const seen = new Set();
  const pushRow = (photoId, title, commentCount) => {
    const id = String(photoId || '').trim();
    const text = String(title || '').trim();
    const key = id || text.slice(0, 48);
    if (!key || seen.has(key)) return;
    seen.add(key);
    rows.push({
      photo_id: id,
      title: text,
      comment_count: commentCount,
    });
  };
  for (const feed of document.querySelectorAll('.comment-home-video')) {
    let photoId = feed.getAttribute('data-photo-id') || feed.dataset?.photoId || '';
    const link = feed.querySelector('a[href*="photoId"], a[href*="workId"]');
    if (!photoId && link) {
      const match = (link.getAttribute('href') || '').match(/(?:photoId|workId)=([A-Za-z0-9_-]+)/);
      if (match) photoId = match[1];
    }
    const title = (feed.innerText || '').split('\\n').map((line) => line.trim()).filter(Boolean)[0] || '';
    let commentCount = 0;
    const countMatch = (feed.innerText || '').match(/(\\d+)\\s*条?评论/);
    if (countMatch) commentCount = parseInt(countMatch[1], 10) || 0;
    pushRow(photoId, title, commentCount);
  }
  return rows;
}
"""

_kuaishou_tab_guard_contexts: set[int] = set()
_kuaishou_guard_main_pages: dict[int, Page] = {}
_kuaishou_popup_blocker_contexts: set[int] = set()


def prune_kuaishou_extra_pages(context, main_page: Page) -> None:
    for extra in list(context.pages):
        if extra == main_page or extra.is_closed():
            continue
        try:
            logger.debug("Pruning stray Kuaishou tab: {}", extra.url)
            extra.close()
        except Exception:
            pass


def install_kuaishou_popup_blocker(context) -> None:
    key = id(context)
    if key in _kuaishou_popup_blocker_contexts:
        return
    _kuaishou_popup_blocker_contexts.add(key)
    context.add_init_script(KUAISHOU_POPUP_BLOCKER_JS)


def _apply_kuaishou_popup_blocker(page: Page) -> None:
    try:
        page.evaluate(KUAISHOU_POPUP_BLOCKER_JS)
    except Exception:
        pass


def bind_kuaishou_tab_guard(context, main_page: Page) -> None:
    """Close stray tabs opened by accidental link navigation during comment reply."""
    key = id(context)
    _kuaishou_guard_main_pages[key] = main_page
    prune_kuaishou_extra_pages(context, main_page)

    if key in _kuaishou_tab_guard_contexts:
        return
    _kuaishou_tab_guard_contexts.add(key)

    def _on_page(new_page) -> None:
        try:
            main = _kuaishou_guard_main_pages.get(id(context))
            if main is None:
                main = main_page
            if new_page != main and not new_page.is_closed():
                logger.info("Closing stray Kuaishou tab: {}", new_page.url)
                new_page.close()
        except Exception:
            pass

    context.on("page", _on_page)


def prepare_kuaishou_comment_page(context, page: Page) -> Page:
    """Install tab/popup guards and close leftover profile tabs before comment automation."""
    install_kuaishou_popup_blocker(context)
    if page.is_closed():
        page = context.pages[0] if context.pages else context.new_page()
    bind_kuaishou_tab_guard(context, page)
    _apply_kuaishou_popup_blocker(page)
    prune_kuaishou_extra_pages(context, page)
    return page


def finalize_kuaishou_comment_page(context, page: Page) -> None:
    prune_kuaishou_extra_pages(context, page)


def _fetch_comment_hub_post_rows(page: Page) -> list[dict[str, Any]]:
    """List posts from the comment hub without visiting content-manage (avoids tab leaks)."""
    _navigate_comment_hub(page)
    dismiss_overlays(page)
    human_pause(page, "page_load")
    page.wait_for_timeout(2000)

    payload = page.evaluate(_FETCH_PHOTO_LIST_JS, 1)
    if isinstance(payload, dict):
        rows = parse_kuaishou_photo_list_payload(payload)
        if rows:
            return rows

    dom_rows = page.evaluate(EXTRACT_COMMENT_HUB_ROWS_JS) or []
    return dom_rows if isinstance(dom_rows, list) else []


def _fetch_work_rows(page: Page) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if PHOTO_LIST_PATH not in response.url or response.status != 200:
            return
        try:
            payload = response.json()
        except Exception:
            return
        if isinstance(payload, dict) and payload.get("result") == 1:
            captured.append(payload)

    page.on("response", on_response)
    try:
        if CONTENT_MANAGE_URL not in page.url:
            page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        else:
            page.reload(wait_until="domcontentloaded", timeout=45_000)
    except Exception:
        pass
    human_pause(page, "page_load")
    page.wait_for_timeout(4000)

    for payload in captured:
        rows = parse_kuaishou_photo_list_payload(payload)
        if rows:
            return rows

    payload = page.evaluate(_FETCH_PHOTO_LIST_JS, 1)
    if isinstance(payload, dict):
        rows = parse_kuaishou_photo_list_payload(payload)
        if rows:
            return rows

    dom_rows = page.evaluate(_EXTRACT_ROWS_JS) or []
    return dom_rows if isinstance(dom_rows, list) else []


def _navigate_comment_hub(page: Page) -> None:
    if COMMENT_HUB_URL not in page.url:
        page.goto(COMMENT_HUB_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
    dismiss_overlays(page)


def _select_video_feed(page: Page, work: dict[str, Any]) -> bool:
    title = str(work.get("title") or "").strip()
    photo_id = str(work.get("photo_id") or work.get("work_id") or "").strip()
    needle = title[:24] if title else ""
    clicked = page.evaluate(CLICK_VIDEO_BY_TITLE_JS, [needle, photo_id])
    human_pause(page, "after_click")
    return bool(isinstance(clicked, dict) and clicked.get("clicked"))


def _select_comment_hub_video_feed(page: Page, work: dict[str, Any]) -> bool:
    title = str(work.get("title") or "").strip()
    photo_id = str(work.get("photo_id") or work.get("work_id") or "").strip()
    needle = title[:24] if title else ""
    clicked = page.evaluate(CLICK_COMMENT_HUB_VIDEO_JS, [needle, photo_id])
    prune_kuaishou_extra_pages(page.context, page)
    human_pause(page, "after_click")
    return bool(isinstance(clicked, dict) and clicked.get("clicked"))


def _find_kuaishou_comment_input(page: Page) -> Locator | None:
    for selector in (
        ".author-comment-input__row__input",
        'textarea[placeholder*="评论"]',
        'div[contenteditable="true"][data-placeholder*="评论"]',
        'div[contenteditable="true"][data-placeholder*="说"]',
    ):
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=1500):
                return loc.first
        except Exception:
            continue
    return None


def _find_kuaishou_submit_button(page: Page) -> Locator | None:
    for locator in (
        page.locator(".author-comment-input__row__btn"),
        page.locator('.author-comment-input__row button:has-text("发布")'),
        page.get_by_role("button", name="发布"),
        page.locator('button:has-text("发送")'),
    ):
        try:
            if locator.count() > 0 and locator.first.is_visible(timeout=800):
                return locator.first
        except Exception:
            continue
    return None


def _prepare_kuaishou_comment_surface(page: Page, work: dict[str, Any]) -> CommentResult | None:
    _navigate_comment_hub(page)
    page.wait_for_timeout(2500)
    if not _select_video_feed(page, work):
        return CommentResult(success=False, error_message="work_not_found")
    page.wait_for_timeout(1500)
    if _find_kuaishou_comment_input(page) is None:
        return CommentResult(success=False, error_message="comment_input_not_found")
    return None


def _fill_and_submit_kuaishou_comment(page: Page, text: str) -> CommentResult:
    comment_input = _find_kuaishou_comment_input(page)
    if comment_input is None:
        return CommentResult(success=False, error_message="comment_input_not_found")

    try:
        human_fill(page, comment_input, text)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"fill_failed:{exc}")

    human_pause(page, "after_type")
    submit = _find_kuaishou_submit_button(page)
    if submit is None:
        return CommentResult(success=False, error_message="submit_button_not_found")

    try:
        human_click(page, submit, timeout_ms=8000)
        human_pause(page, "after_click")
    except Exception as exc:
        return CommentResult(success=False, error_message=f"submit_click_failed:{exc}")

    logger.info("快手首评已提交")
    return CommentResult(success=True)


def post_kuaishou_first_comment(
    page: Page,
    *,
    text: str,
    title: str,
    photo_id: str | None = None,
    delay_sec: int = 15,
    wait_max_sec: int = 60,
    dry_run: bool = False,
) -> CommentResult:
    cleaned = (text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_comment_text")

    real_id = None if is_synthetic_platform_post_id(photo_id) else photo_id
    work = {"photo_id": real_id, "title": title}

    if title.strip() or real_id:
        prep_error = _prepare_kuaishou_comment_surface(page, work)
        if prep_error is None:
            if dry_run:
                return CommentResult(success=True)
            return _fill_and_submit_kuaishou_comment(page, cleaned)
        if prep_error.error_message != "work_not_found":
            return prep_error

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

    prep_error = _prepare_kuaishou_comment_surface(page, polled)
    if prep_error is not None:
        return prep_error
    if dry_run:
        return CommentResult(success=True)
    return _fill_and_submit_kuaishou_comment(page, cleaned)
