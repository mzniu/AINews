"""Douyin creator audience comment fetch (API) and reply (UI)."""
from __future__ import annotations

import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.douyin_comment import (
    _dismiss_overlays,
    _fetch_work_rows,
    _open_comment_page_for_work,
    _pick_work,
)
from services.publishing.comment_reply.types import InboundComment, PostCommentSession
from services.publishing.human_form import human_fill
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.douyin import CONTENT_MANAGE_URL
from services.publishing.metrics.post_id import is_synthetic_platform_post_id

if True:
    from playwright.sync_api import Locator, Page

COMMENT_LIST_PATH_FRAGMENT = "/comment/read/aweme/v1/web/comment/list/select"
COMMENT_REPLY_PATH_FRAGMENT = "/comment/read/aweme/v1/web/comment/list/reply"

_FETCH_COMMENT_LIST_JS = """
async ([awemeId, cursor]) => {
  const params = new URLSearchParams({
    aweme_id: String(awemeId || ''),
    cursor: String(cursor ?? 0),
    count: '20',
    comment_select_options: '0',
    sort_options: '0',
    channel_id: '618',
    app_id: '2906',
    aid: '2906',
    device_platform: 'webapp',
  });
  const url = `https://creator.douyin.com/web/api/third_party/aweme/api/comment/read/aweme/v1/web/comment/list/select/?${params}`;
  const resp = await fetch(url, { credentials: 'include' });
  if (!resp.ok) {
    return { error: resp.status, status_text: resp.statusText };
  }
  return await resp.json();
}
"""

_FETCH_COMMENT_REPLY_LIST_JS = """
async ([itemId, commentId, cursor]) => {
  const params = new URLSearchParams({
    item_id: String(itemId || ''),
    comment_id: String(commentId || ''),
    cursor: String(cursor ?? 0),
    count: '20',
    item_type: '0',
    channel_id: '618',
    app_id: '2906',
    aid: '2906',
    device_platform: 'webapp',
  });
  const url = `https://creator.douyin.com/web/api/third_party/aweme/api/comment/read/aweme/v1/web/comment/list/reply/?${params}`;
  const resp = await fetch(url, { credentials: 'include' });
  if (!resp.ok) {
    return { error: resp.status, status_text: resp.statusText };
  }
  return await resp.json();
}
"""

CLICK_DOUYIN_REPLY_JS = """
([commentId, contentNeedle]) => {
  const idNeedle = String(commentId || '').trim();
  const textNeedle = String(contentNeedle || '').trim().slice(0, 40);
  const isHit = (text) => {
    if (idNeedle && text.includes(idNeedle)) return true;
    return textNeedle && text.includes(textNeedle);
  };
  for (const el of document.querySelectorAll('[class*="comment"], [class*="Comment"], li, div')) {
    const text = (el.innerText || '').trim();
    if (!text || text.length < 4 || text.length > 600) continue;
    if (/有爱评论|说点好听的|全部评论|批量管理|评论管理/.test(text)) continue;
    if (!isHit(text)) continue;
    const scope = el.closest('[class*="comment"]') || el;
    for (const btn of scope.querySelectorAll('span, button, a, div')) {
      const label = (btn.innerText || '').trim();
      if (label !== '回复') continue;
      try {
        btn.scrollIntoView({ block: 'center', inline: 'nearest' });
      } catch (err) {}
      btn.click();
      return { clicked: true, mode: 'reply_btn' };
    }
  }
  return { clicked: false };
}
"""

CLICK_REPLY_SUBMIT_JS = """
() => {
  const active = document.activeElement;
  const topInput = document.querySelector(
    'div.input-d24X73, [placeholder*="有爱评论"], [data-placeholder*="有爱评论"]'
  );
  const topRect = topInput ? topInput.getBoundingClientRect() : null;
  const candidates = [];
  for (const el of document.querySelectorAll('button, span, a, div[role="button"]')) {
    const label = (el.innerText || '').trim();
    if (label !== '发送') continue;
    if (!el.offsetParent) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) continue;
    if (topRect && Math.abs(rect.top - topRect.top) < 100) continue;
    if (topInput && topInput.contains(el)) continue;
    let distance = 99999;
    if (active) {
      const ar = active.getBoundingClientRect();
      const dx = rect.left - ar.left;
      const dy = rect.top - ar.top;
      distance = Math.sqrt(dx * dx + dy * dy);
    }
    candidates.push({ el, distance, top: rect.top });
  }
  if (!candidates.length) return { clicked: false };
  candidates.sort((a, b) => a.distance - b.distance || b.top - a.top);
  candidates[0].el.click();
  return { clicked: true, distance: candidates[0].distance };
}
"""


def _nickname_matches(account_nickname: str | None, candidate: str | None) -> bool:
    account_name = (account_nickname or "").strip()
    other = (candidate or "").strip()
    if not account_name or not other:
        return False
    if account_name == other:
        return True
    # Creator display names may include suffixes like "未来读书人·官方".
    return account_name in other or other in account_name


def _reply_text_snippet(reply_text: str | None) -> str:
    return re.sub(r"\s+", "", str(reply_text or "").strip())[:24]


def _reply_text_in_douyin_payload(payload: dict[str, Any], expected_reply_text: str | None) -> bool:
    needle = _reply_text_snippet(expected_reply_text)
    if len(needle) < 4:
        return False
    for item in payload.get("comments") or []:
        if not isinstance(item, dict):
            continue
        text = re.sub(r"\s+", "", str(item.get("text") or item.get("content") or ""))
        if needle in text:
            return True
    return False


def _author_replied_in_douyin_reply_payload(
    payload: dict[str, Any],
    account_nickname: str | None,
    *,
    expected_reply_text: str | None = None,
) -> bool:
    if not payload or payload.get("error"):
        return False
    if int(payload.get("status_code") or 0) != 0:
        return False
    if _reply_text_in_douyin_payload(payload, expected_reply_text):
        return True
    for item in payload.get("comments") or []:
        if not isinstance(item, dict):
            continue
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        nickname = str(user.get("nickname") or user.get("nick_name") or "").strip()
        if _nickname_matches(account_nickname, nickname):
            return True
    return False


def _author_replied_in_douyin_item(
    item: dict[str, Any],
    account_nickname: str | None,
    *,
    expected_reply_text: str | None = None,
) -> bool:
    reply_comment = item.get("reply_comment")
    if isinstance(reply_comment, dict):
        reply_text = str(reply_comment.get("text") or reply_comment.get("content") or "").strip()
        needle = _reply_text_snippet(expected_reply_text)
        if needle and needle in re.sub(r"\s+", "", reply_text):
            return True
        user = reply_comment.get("user") if isinstance(reply_comment.get("user"), dict) else {}
        nickname = str(
            user.get("nickname")
            or user.get("nick_name")
            or reply_comment.get("nickname")
            or ""
        ).strip()
        if _nickname_matches(account_nickname, nickname):
            return True
    return False


def douyin_author_already_replied_in_thread(
    page: Page,
    *,
    video_id: str,
    comment_id: str,
    account_nickname: str | None,
    raw_item: dict[str, Any] | None = None,
    expected_reply_text: str | None = None,
) -> bool:
    if raw_item and _author_replied_in_douyin_item(
        raw_item,
        account_nickname,
        expected_reply_text=expected_reply_text,
    ):
        return True
    if raw_item and int(raw_item.get("reply_comment_total") or 0) <= 0 and not raw_item.get("reply_comment"):
        return False

    cursor = 0
    for _page in range(5):
        payload = page.evaluate(_FETCH_COMMENT_REPLY_LIST_JS, [video_id, comment_id, cursor])
        if not isinstance(payload, dict):
            break
        if _author_replied_in_douyin_reply_payload(
            payload,
            account_nickname,
            expected_reply_text=expected_reply_text,
        ):
            return True
        if int(payload.get("status_code") or 0) != 0:
            break
        if not payload.get("has_more"):
            break
        next_cursor = payload.get("cursor")
        if next_cursor is None or next_cursor == cursor:
            break
        cursor = int(next_cursor)
        time.sleep(0.1)
    return False


def _apply_douyin_reply_state(
    page: Page,
    *,
    video_id: str,
    comment: InboundComment,
    raw_item: dict[str, Any] | None,
    account_nickname: str | None,
) -> InboundComment:
    if comment.already_replied_by_author:
        return comment
    if raw_item is None:
        raw_item = {}
    if int(raw_item.get("reply_comment_total") or 0) <= 0 and not raw_item.get("reply_comment"):
        return comment
    if douyin_author_already_replied_in_thread(
        page,
        video_id=video_id,
        comment_id=comment.platform_comment_id,
        account_nickname=account_nickname,
        raw_item=raw_item,
    ):
        return replace(comment, already_replied_by_author=True)
    return comment


def _parse_comment_time(raw: Any) -> datetime | None:
    if raw is None:
        return None
    try:
        ts = int(str(raw).strip())
    except ValueError:
        return None
    if ts > 10_000_000_000:
        ts = ts // 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def parse_douyin_comment_list_payload(
    payload: dict[str, Any],
    *,
    video_id: str,
    post_title: str | None,
    account_nickname: str | None,
) -> list[InboundComment]:
    if not payload or payload.get("error"):
        return []
    if int(payload.get("status_code") or 0) != 0:
        return []

    results: list[InboundComment] = []
    for item in payload.get("comments") or []:
        if not isinstance(item, dict):
            continue
        comment_id = str(item.get("cid") or item.get("comment_id") or "").strip()
        content = str(item.get("text") or item.get("content") or "").strip()
        if not comment_id or not content:
            continue
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        author = str(user.get("nickname") or user.get("nick_name") or "").strip() or None
        already_replied = _author_replied_in_douyin_item(item, account_nickname)
        results.append(
            InboundComment(
                platform_post_id=video_id,
                platform_comment_id=comment_id,
                author_name=author,
                content=content,
                commented_at=_parse_comment_time(item.get("create_time")),
                post_title=post_title,
                already_replied_by_author=already_replied,
            )
        )
    return results


def _capture_comment_payloads(page: Page, action) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if response.status != 200:
            return
        if COMMENT_LIST_PATH_FRAGMENT not in (response.url or ""):
            return
        try:
            payload = response.json()
        except Exception:
            return
        if isinstance(payload, dict):
            captured.append(payload)

    page.on("response", on_response)
    try:
        action()
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    return captured


def fetch_douyin_comments_for_post(
    page: Page,
    *,
    video_id: str,
    post_title: str | None,
    account_nickname: str | None,
) -> list[InboundComment]:
    if is_synthetic_platform_post_id(video_id):
        return []

    results: list[InboundComment] = []
    seen: set[str] = set()
    cursor = 0
    for _page in range(15):
        payload = page.evaluate(_FETCH_COMMENT_LIST_JS, [video_id, cursor])
        if not isinstance(payload, dict):
            break
        raw_items = {
            str(item.get("cid") or item.get("comment_id") or "").strip(): item
            for item in (payload.get("comments") or [])
            if isinstance(item, dict)
        }
        batch = parse_douyin_comment_list_payload(
            payload,
            video_id=video_id,
            post_title=post_title,
            account_nickname=account_nickname,
        )
        for item in batch:
            if item.platform_comment_id in seen:
                continue
            seen.add(item.platform_comment_id)
            enriched = _apply_douyin_reply_state(
                page,
                video_id=video_id,
                comment=item,
                raw_item=raw_items.get(item.platform_comment_id),
                account_nickname=account_nickname,
            )
            results.append(enriched)
        if int(payload.get("status_code") or 0) != 0:
            break
        if not payload.get("has_more"):
            break
        next_cursor = payload.get("cursor")
        if next_cursor is None or next_cursor == cursor:
            break
        cursor = int(next_cursor)
        time.sleep(0.15)
    return results


def _navigate_comment_hub(page: Page) -> None:
    page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    human_pause(page, "page_load")
    _dismiss_overlays(page)


def reset_douyin_comment_reply_ui(page: Page) -> None:
    _dismiss_overlays(page)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(500)


def _find_douyin_reply_input(page: Page) -> Locator | None:
    try:
        focused = page.locator(":focus")
        if focused.count() > 0:
            item = focused.first
            if item.is_visible(timeout=500):
                hint = item.evaluate(
                    """(el) => [
                      el.getAttribute('placeholder'),
                      el.getAttribute('data-placeholder'),
                      el.getAttribute('aria-label'),
                    ].filter(Boolean).join(' ')"""
                )
                if "有爱评论" not in (hint or "") and "说点好听" not in (hint or ""):
                    tag = item.evaluate("(el) => el.tagName")
                    editable = item.evaluate("(el) => !!el.isContentEditable")
                    if tag in {"TEXTAREA", "INPUT"} or editable:
                        return item
    except Exception:
        pass

    for selector in (
        '[class*="reply"] textarea',
        '[class*="reply"] [contenteditable="true"]',
        '[class*="Reply"] textarea',
        '[class*="Reply"] [contenteditable="true"]',
        'textarea[placeholder*="回复"]',
        'div[contenteditable="true"][data-placeholder*="回复"]',
        'textarea[placeholder*="评论"]',
    ):
        loc = page.locator(selector)
        try:
            count = loc.count()
        except Exception:
            continue
        for idx in range(min(count, 8)):
            item = loc.nth(idx)
            try:
                if not item.is_visible(timeout=600):
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
            if "有爱评论" in (hint or "") or "说点好听" in (hint or ""):
                continue
            return item
    return None


def _wait_for_douyin_reply_input(page: Page, *, timeout_ms: int = 6000) -> Locator | None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        reply_input = _find_douyin_reply_input(page)
        if reply_input is not None:
            return reply_input
        page.wait_for_timeout(300)
    return None


def _click_douyin_reply_submit(page: Page) -> bool:
    for _attempt in range(3):
        clicked = page.evaluate(CLICK_REPLY_SUBMIT_JS)
        if isinstance(clicked, dict) and clicked.get("clicked"):
            return True
        page.wait_for_timeout(500)
    return False


def _verify_douyin_reply_cleared(page: Page, reply_text: str) -> bool:
    needle = (reply_text or "").strip()[:12]
    if not needle:
        return True
    try:
        remaining = page.evaluate(
            """() => {
              const active = document.activeElement;
              if (!active) return '';
              return String(active.value || active.innerText || '').trim();
            }"""
        )
    except Exception:
        return True
    return needle not in str(remaining or "")


def activate_douyin_post_session(page: Page, *, post_row: dict[str, Any]) -> PostCommentSession:
    video_id = str(post_row.get("video_id") or post_row.get("work_id") or "").strip()
    post_title = str(post_row.get("title") or "").strip()
    work = {"video_id": video_id, "title": post_title, "comment_count": post_row.get("comment_count")}

    captured = _capture_comment_payloads(page, lambda: _open_comment_page_for_work(page, work))
    feed_active = bool(captured)
    if not feed_active:
        feed_active = _open_comment_page_for_work(page, work)
    if not feed_active:
        _dismiss_overlays(page)
        page.wait_for_timeout(1200)
        captured = _capture_comment_payloads(page, lambda: _open_comment_page_for_work(page, work))
        feed_active = bool(captured) or _open_comment_page_for_work(page, work)

    page.wait_for_timeout(2000)
    return PostCommentSession(
        platform_post_id=video_id,
        post_title=post_title or None,
        hub_feed_text=None,
        feed_match_spec=None,
        feed_active=feed_active,
        post_context_json=None,
    )


def _douyin_reply_visible_on_platform(
    page: Page,
    *,
    video_id: str,
    comment_id: str,
    account_nickname: str | None,
    expected_reply_text: str | None = None,
) -> bool:
    return douyin_author_already_replied_in_thread(
        page,
        video_id=video_id,
        comment_id=comment_id,
        account_nickname=account_nickname,
        expected_reply_text=expected_reply_text,
    )


def _resolve_douyin_submit_result(
    page: Page,
    *,
    video_id: str,
    comment: InboundComment,
    account_nickname: str | None,
    verified: bool,
    error_message: str,
    reply_text: str | None = None,
) -> CommentResult:
    if verified:
        return CommentResult(success=True, comment_id=comment.platform_comment_id)
    if _douyin_reply_visible_on_platform(
        page,
        video_id=video_id,
        comment_id=comment.platform_comment_id,
        account_nickname=account_nickname,
        expected_reply_text=reply_text,
    ):
        logger.info(
            "抖音评论回复已在平台可见，按成功处理 comment_id={}",
            comment.platform_comment_id,
        )
        return CommentResult(success=True, comment_id=comment.platform_comment_id)
    return CommentResult(success=False, error_message=error_message)


def reply_douyin_audience_comment_on_active_feed(
    page: Page,
    *,
    session: PostCommentSession,
    comment: InboundComment,
    reply_text: str,
    account_nickname: str | None = None,
) -> CommentResult:
    if not session.feed_active:
        return CommentResult(success=False, error_message="feed_not_active")

    cleaned = (reply_text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_reply_text")

    if comment.already_replied_by_author or douyin_author_already_replied_in_thread(
        page,
        video_id=session.platform_post_id,
        comment_id=comment.platform_comment_id,
        account_nickname=account_nickname,
        expected_reply_text=cleaned,
    ):
        return CommentResult(success=False, error_message="already_replied")

    reset_douyin_comment_reply_ui(page)
    clicked = page.evaluate(
        CLICK_DOUYIN_REPLY_JS,
        [comment.platform_comment_id, comment.content[:40]],
    )
    if not (isinstance(clicked, dict) and clicked.get("clicked")):
        reset_douyin_comment_reply_ui(page)
        page.wait_for_timeout(1000)
        clicked = page.evaluate(
            CLICK_DOUYIN_REPLY_JS,
            [comment.platform_comment_id, comment.content[:40]],
        )
    if not (isinstance(clicked, dict) and clicked.get("clicked")):
        return CommentResult(success=False, error_message="reply_button_not_found")

    human_pause(page, "after_click")
    reply_input = _wait_for_douyin_reply_input(page)
    if reply_input is None:
        return CommentResult(success=False, error_message="reply_input_not_found")

    try:
        human_fill(page, reply_input, cleaned)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"fill_failed:{exc}")

    human_pause(page, "after_type")
    if not _click_douyin_reply_submit(page):
        return CommentResult(success=False, error_message="submit_button_not_found")

    page.wait_for_timeout(1200)
    if not _verify_douyin_reply_cleared(page, cleaned):
        if not _click_douyin_reply_submit(page):
            return _resolve_douyin_submit_result(
                page,
                video_id=session.platform_post_id,
                comment=comment,
                account_nickname=account_nickname,
                verified=False,
                error_message="submit_not_confirmed",
                reply_text=cleaned,
            )
        page.wait_for_timeout(1200)
        if not _verify_douyin_reply_cleared(page, cleaned):
            return _resolve_douyin_submit_result(
                page,
                video_id=session.platform_post_id,
                comment=comment,
                account_nickname=account_nickname,
                verified=False,
                error_message="submit_not_confirmed",
                reply_text=cleaned,
            )

    human_pause(page, "after_click")
    logger.info("抖音观众评论回复已提交 comment_id={}", comment.platform_comment_id)
    reset_douyin_comment_reply_ui(page)
    return CommentResult(success=True, comment_id=comment.platform_comment_id)


def reply_douyin_audience_comment(
    page: Page,
    *,
    video_id: str,
    post_title: str,
    platform_comment_id: str,
    comment_content: str,
    reply_text: str,
    account_nickname: str | None = None,
) -> CommentResult:
    cleaned = (reply_text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_reply_text")

    _navigate_comment_hub(page)
    page.wait_for_timeout(2000)
    session = activate_douyin_post_session(
        page,
        post_row={"video_id": video_id, "title": post_title},
    )
    if not session.feed_active:
        return CommentResult(success=False, error_message="work_not_found")

    return reply_douyin_audience_comment_on_active_feed(
        page,
        session=session,
        comment=InboundComment(
            platform_post_id=video_id,
            platform_comment_id=platform_comment_id,
            author_name="",
            content=comment_content,
            commented_at=None,
        ),
        reply_text=cleaned,
        account_nickname=account_nickname,
    )


def scan_douyin_post_rows(page: Page, *, max_posts: int) -> list[dict[str, Any]]:
    return _fetch_work_rows(page)[:max_posts]


def scan_douyin_account_comments(
    page: Page,
    *,
    account_nickname: str | None,
    max_posts: int,
) -> list[tuple[dict[str, Any], list[InboundComment]]]:
    _navigate_comment_hub(page)
    rows = _fetch_work_rows(page)[:max_posts]
    batches: list[tuple[dict[str, Any], list[InboundComment]]] = []
    for row in rows:
        video_id = str(row.get("video_id") or "").strip()
        if not video_id or is_synthetic_platform_post_id(video_id):
            continue
        if int(row.get("comment_count") or 0) <= 0:
            continue
        title = str(row.get("title") or "").strip()
        session = activate_douyin_post_session(page, post_row=row)
        if not session.feed_active:
            continue
        comments = fetch_douyin_comments_for_post(
            page,
            video_id=video_id,
            post_title=title,
            account_nickname=account_nickname,
        )
        batches.append((row, comments))
        time.sleep(0.3)
    return batches
