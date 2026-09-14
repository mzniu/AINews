"""Kuaishou audience comment fetch and reply (UI + API intercept)."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.creator_comment_helpers import dismiss_overlays
from services.publishing.adapters.kuaishou_comment import (
    COMMENT_HUB_URL,
    _fetch_comment_hub_post_rows,
    _navigate_comment_hub,
    _select_comment_hub_video_feed,
    finalize_kuaishou_comment_page,
    prepare_kuaishou_comment_page,
    prune_kuaishou_extra_pages,
)
from services.publishing.comment_reply.types import InboundComment, PostCommentSession
from services.publishing.human_form import human_fill
from services.publishing.human_interaction import human_click
from services.publishing.human_pacing import human_pause

if True:
    from playwright.sync_api import Locator, Page

COMMENT_LIST_PATH_FRAGMENTS = (
    "/comment/list",
    "/works/comment",
    "/works/v2/comment",
)

EXTRACT_KUAISHOU_AUDIENCE_COMMENTS_JS = """
() => {
  const rows = [];
  const seen = new Set();
  const push = (id, author, content) => {
    const text = String(content || '').trim();
    const name = String(author || '').trim();
    if (!text) return;
    const cid = String(id || '').trim() || `hash:${name}:${text.slice(0, 48)}`;
    if (seen.has(cid)) return;
    seen.add(cid);
    rows.push({ comment_id: cid, author_name: name, content: text });
  };
  const selectors = [
    '.comment-list-item',
    '.comment-item',
    '[class*="CommentItem"]',
    '[class*="comment-item"]',
  ];
  for (const selector of selectors) {
    for (const el of document.querySelectorAll(selector)) {
      if (el.closest('.author-comment-input')) continue;
      const id = el.getAttribute('data-comment-id') || el.dataset?.commentId;
      const authorEl = el.querySelector('[class*="nickname"], [class*="user-name"], .name, .username');
      const contentEl = el.querySelector('[class*="content"], [class*="text"], p');
      const author = authorEl ? authorEl.innerText.trim() : '';
      let content = contentEl ? contentEl.innerText.trim() : '';
      if (!content) {
        content = (el.innerText || '').replace(/回复/g, '').trim();
      }
      push(id, author, content);
    }
  }
  return rows;
}
"""

CLICK_KUAISHOU_REPLY_JS = """
([commentId, contentNeedle]) => {
  const idNeedle = String(commentId || '').trim();
  const textNeedle = String(contentNeedle || '').trim().slice(0, 40);
  for (const el of document.querySelectorAll('.comment-item, .comment-list-item, [class*="comment-item"]')) {
    if (el.closest('.author-comment-input')) continue;
    const text = (el.innerText || '').trim();
    const cid = el.getAttribute('data-comment-id') || el.dataset?.commentId || '';
    const hit = (idNeedle && cid === idNeedle) || (textNeedle && text.includes(textNeedle));
    if (!hit) continue;
    for (const btn of el.querySelectorAll('button, span, a, div')) {
      if ((btn.innerText || '').trim() === '回复') {
        btn.click();
        return { clicked: true };
      }
    }
  }
  return { clicked: false };
}
"""


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


def _stable_comment_id(photo_id: str, author: str | None, content: str) -> str:
    digest = hashlib.sha1(f"{photo_id}|{author or ''}|{content}".encode("utf-8")).hexdigest()
    return f"ks_{digest[:24]}"


def _author_already_replied(items: list[dict[str, Any]], account_nickname: str | None) -> bool:
    account_name = (account_nickname or "").strip()
    if not account_name:
        return False
    for item in items:
        author = str(item.get("author_name") or item.get("userName") or "").strip()
        if author == account_name:
            return True
    return False


def parse_kuaishou_comment_list_payload(
    payload: dict[str, Any],
    *,
    photo_id: str,
    post_title: str | None,
    account_nickname: str | None,
) -> list[InboundComment]:
    if not payload:
        return []
    result_code = payload.get("result")
    if result_code not in (None, 1, "1"):
        return []
    data = payload.get("data") or {}
    rows = (
        data.get("list")
        or data.get("comments")
        or data.get("commentList")
        or payload.get("comments")
        or []
    )
    results: list[InboundComment] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        content = str(
            item.get("content")
            or item.get("commentContent")
            or item.get("text")
            or ""
        ).strip()
        if not content:
            continue
        author = str(
            item.get("userName")
            or item.get("authorName")
            or item.get("nickname")
            or ""
        ).strip() or None
        comment_id = str(
            item.get("commentId")
            or item.get("id")
            or item.get("comment_id")
            or ""
        ).strip()
        if not comment_id:
            comment_id = _stable_comment_id(photo_id, author, content)
        replies = item.get("replyList") or item.get("subComments") or []
        results.append(
            InboundComment(
                platform_post_id=photo_id,
                platform_comment_id=comment_id,
                author_name=author,
                content=content,
                commented_at=_parse_comment_time(
                    item.get("timestamp") or item.get("createTime") or item.get("commentTime")
                ),
                post_title=post_title,
                already_replied_by_author=_author_already_replied(
                    replies if isinstance(replies, list) else [],
                    account_nickname,
                ),
            )
        )
    return results


def _select_video_feed(page: Page, work: dict[str, Any]) -> bool:
    return _select_comment_hub_video_feed(page, work)


def _capture_comment_payloads(page: Page, action) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if response.status != 200:
            return
        if not any(fragment in response.url for fragment in COMMENT_LIST_PATH_FRAGMENTS):
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


def fetch_kuaishou_comments_for_post(
    page: Page,
    *,
    photo_id: str,
    post_title: str | None,
    account_nickname: str | None,
    skip_feed_select: bool = False,
) -> list[InboundComment]:
    work = {"photo_id": photo_id, "title": post_title or ""}
    if skip_feed_select:
        page.wait_for_timeout(500)
        payloads: list[dict[str, Any]] = []
    else:
        payloads = _capture_comment_payloads(
            page,
            lambda: _select_video_feed(page, work),
        )
    page.wait_for_timeout(2000)
    for payload in payloads:
        rows = parse_kuaishou_comment_list_payload(
            payload,
            photo_id=photo_id,
            post_title=post_title,
            account_nickname=account_nickname,
        )
        if rows:
            return rows

    dom_rows = page.evaluate(EXTRACT_KUAISHOU_AUDIENCE_COMMENTS_JS) or []
    results: list[InboundComment] = []
    if isinstance(dom_rows, list):
        for item in dom_rows:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            author = str(item.get("author_name") or "").strip() or None
            comment_id = str(item.get("comment_id") or "").strip()
            if not comment_id:
                comment_id = _stable_comment_id(photo_id, author, content)
            results.append(
                InboundComment(
                    platform_post_id=photo_id,
                    platform_comment_id=comment_id,
                    author_name=author,
                    content=content,
                    commented_at=None,
                    post_title=post_title,
                )
            )
    return results


def _find_kuaishou_reply_input(page: Page) -> Locator | None:
    for selector in (
        'textarea[placeholder*="回复"]',
        'div[contenteditable="true"][data-placeholder*="回复"]',
        'textarea[class*="reply"]',
        'textarea',
    ):
        loc = page.locator(selector)
        try:
            count = loc.count()
        except Exception:
            continue
        for idx in range(count):
            candidate = loc.nth(idx)
            try:
                if candidate.is_visible(timeout=800) and not candidate.evaluate(
                    "el => !!el.closest('.author-comment-input')"
                ):
                    return candidate
            except Exception:
                continue
    return None


def _find_kuaishou_reply_submit(page: Page) -> Locator | None:
    for locator in (
        page.locator('button:has-text("发送")'),
        page.locator('button:has-text("发布")'),
        page.locator('[class*="reply"] button:has-text("发送")'),
    ):
        try:
            if locator.count() > 0 and locator.first.is_visible(timeout=800):
                return locator.first
        except Exception:
            continue
    return None


def reset_kuaishou_comment_reply_ui(page: Page) -> None:
    dismiss_overlays(page)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(500)


def activate_kuaishou_post_session(page: Page, *, post_row: dict[str, Any]) -> PostCommentSession:
    photo_id = str(post_row.get("photo_id") or post_row.get("work_id") or "").strip()
    post_title = str(post_row.get("title") or "").strip()
    feed_active = _select_video_feed(page, post_row)
    if not feed_active:
        dismiss_overlays(page)
        page.wait_for_timeout(1200)
        feed_active = _select_video_feed(page, post_row)
    prune_kuaishou_extra_pages(page.context, page)
    page.wait_for_timeout(2000)
    return PostCommentSession(
        platform_post_id=photo_id,
        post_title=post_title or None,
        hub_feed_text=None,
        feed_match_spec=None,
        feed_active=feed_active,
        post_context_json=None,
    )


def reply_kuaishou_audience_comment_on_active_feed(
    page: Page,
    *,
    session: PostCommentSession,
    comment: InboundComment,
    reply_text: str,
) -> CommentResult:
    if not session.feed_active:
        return CommentResult(success=False, error_message="feed_not_active")

    cleaned = (reply_text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_reply_text")

    if comment.already_replied_by_author:
        return CommentResult(success=False, error_message="already_replied")

    reset_kuaishou_comment_reply_ui(page)
    clicked = page.evaluate(
        CLICK_KUAISHOU_REPLY_JS,
        [comment.platform_comment_id, comment.content[:40]],
    )
    if not (isinstance(clicked, dict) and clicked.get("clicked")):
        reset_kuaishou_comment_reply_ui(page)
        page.wait_for_timeout(1000)
        clicked = page.evaluate(
            CLICK_KUAISHOU_REPLY_JS,
            [comment.platform_comment_id, comment.content[:40]],
        )
    if not (isinstance(clicked, dict) and clicked.get("clicked")):
        return CommentResult(success=False, error_message="reply_button_not_found")

    human_pause(page, "after_click")
    reply_input = _find_kuaishou_reply_input(page)
    if reply_input is None:
        return CommentResult(success=False, error_message="reply_input_not_found")

    try:
        human_fill(page, reply_input, cleaned)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"fill_failed:{exc}")

    human_pause(page, "after_type")
    submit = _find_kuaishou_reply_submit(page)
    if submit is None:
        return CommentResult(success=False, error_message="submit_button_not_found")

    try:
        human_click(page, submit, timeout_ms=8000)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"submit_click_failed:{exc}")

    human_pause(page, "after_click")
    logger.info("快手观众评论回复已提交 comment_id={}", comment.platform_comment_id)
    reset_kuaishou_comment_reply_ui(page)
    prune_kuaishou_extra_pages(page.context, page)
    return CommentResult(success=True, comment_id=comment.platform_comment_id)


def reply_kuaishou_audience_comment(
    page: Page,
    *,
    photo_id: str,
    post_title: str,
    platform_comment_id: str,
    comment_content: str,
    reply_text: str,
) -> CommentResult:
    cleaned = (reply_text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_reply_text")

    page = prepare_kuaishou_comment_page(page.context, page)
    _navigate_comment_hub(page)
    page.wait_for_timeout(2000)
    session = activate_kuaishou_post_session(
        page,
        post_row={"photo_id": photo_id, "title": post_title},
    )
    if not session.feed_active:
        return CommentResult(success=False, error_message="work_not_found")

    result = reply_kuaishou_audience_comment_on_active_feed(
        page,
        session=session,
        comment=InboundComment(
            platform_post_id=photo_id,
            platform_comment_id=platform_comment_id,
            author_name="",
            content=comment_content,
            commented_at=None,
        ),
        reply_text=cleaned,
    )
    finalize_kuaishou_comment_page(page.context, page)
    return result


def scan_kuaishou_post_rows(page: Page, *, max_posts: int) -> list[dict[str, Any]]:
    return _fetch_comment_hub_post_rows(page)[:max_posts]


def scan_kuaishou_account_comments(
    page: Page,
    *,
    account_nickname: str | None,
    max_posts: int,
) -> list[tuple[dict[str, Any], list[InboundComment]]]:
    page = prepare_kuaishou_comment_page(page.context, page)
    _navigate_comment_hub(page)
    dismiss_overlays(page)
    rows = _fetch_comment_hub_post_rows(page)[:max_posts]
    batches: list[tuple[dict[str, Any], list[InboundComment]]] = []
    for row in rows:
        photo_id = str(row.get("photo_id") or row.get("work_id") or "").strip()
        if not photo_id:
            continue
        if int(row.get("comment_count") or 0) <= 0:
            continue
        title = str(row.get("title") or "").strip()
        session = activate_kuaishou_post_session(page, post_row=row)
        if not session.feed_active:
            continue
        comments = fetch_kuaishou_comments_for_post(
            page,
            photo_id=photo_id,
            post_title=title,
            account_nickname=account_nickname,
            skip_feed_select=True,
        )
        batches.append((row, comments))
        prune_kuaishou_extra_pages(page.context, page)
        time.sleep(0.3)
    finalize_kuaishou_comment_page(page.context, page)
    return batches
