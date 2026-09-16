"""WeChat Channels audience comment fetch (API) and reply (UI)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.creator_comment_helpers import dismiss_overlays
from services.publishing.adapters.wechat_channels_comment import (
    COMMENT_HUB_URL,
    SCROLL_COMMENT_FEED_LIST_JS,
    _dismiss_wechat_tip,
    _navigate_comment_hub,
)
from services.publishing.comment_reply.types import InboundComment, PostCommentSession
from services.publishing.human_form import human_fill
from services.publishing.human_interaction import human_click
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.wechat_channels import (
    _FETCH_POST_LIST_JS,
    parse_wechat_post_list_payload,
)

if True:
    from playwright.sync_api import Page

COMMENT_LIST_API = "https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/comment/comment_list"

_UPDATE_FEED_COMMENT_JS = """
async (exportId) => {
  const raw = String(exportId || '').trim();
  if (!raw) return { errCode: -1, errMsg: 'missing_export_id' };
  const normalized = raw.startsWith('export/') ? raw : `export/${raw}`;
  const body = {
    opType: 1,
    exportId: normalized,
    timestamp: String(Date.now()),
    scene: 7,
    reqScene: 7,
  };
  const urls = [
    'https://channels.weixin.qq.com/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/update_feed_comment',
    'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/comment/update_feed_comment',
  ];
  let last = null;
  for (const url of urls) {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        last = { errCode: resp.status, errMsg: resp.statusText, _url: url };
        continue;
      }
      const data = await resp.json();
      if (data && (data.errCode === 0 || data.errCode === undefined)) {
        return { ...data, _url: url };
      }
      last = { ...data, _url: url };
    } catch (err) {
      last = { errCode: -1, errMsg: String(err), _url: url };
    }
  }
  return last || { errCode: -1, errMsg: 'update_feed_comment_failed' };
}
"""

_FETCH_COMMENT_LIST_JS = """
async ([exportId, lastBuff]) => {
  const raw = String(exportId || '').trim();
  const normalized = raw.startsWith('export/') ? raw : `export/${raw}`;
  const body = {
    exportId: normalized,
    lastBuff: lastBuff || '',
    commentSelection: false,
    forMcn: false,
    timestamp: Date.now(),
    scene: 7,
    reqScene: 7,
  };
  const urls = [
    'https://channels.weixin.qq.com/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/comment_list',
    'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/comment/comment_list',
  ];
  let last = null;
  for (const url of urls) {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        last = { error: resp.status, status_text: resp.statusText, _url: url };
        continue;
      }
      const data = await resp.json();
      if (data && (data.errCode === 0 || data.errCode === undefined)) {
        return data;
      }
      last = data;
    } catch (err) {
      last = { error: -1, status_text: String(err) };
    }
  }
  return last;
}
"""

_COUNT_AUDIENCE_COMMENTS_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  let count = 0;
  for (const root of roots) {
    for (const el of root.querySelectorAll('.comment-item, .comment-list-item, [class*="comment-item"]')) {
      if (el.closest('.author-comment-input, .comment-create-wrap')) continue;
      const text = (el.innerText || '').trim();
      if (text) count += 1;
    }
  }
  return count;
}
"""

_WAIT_WUJIE_COMMENT_HUB_JS = """
() => {
  const wujie = document.querySelector('wujie-app');
  if (!wujie || !wujie.shadowRoot) return false;
  return wujie.shadowRoot.querySelector('.comment-feed-wrap') !== null;
}
"""

SCORE_AND_CLICK_BEST_FEED_JS = """
([matchSpec, exportId]) => {
  const required = (matchSpec?.required || [])
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item) => item.length >= 4);
  const preferred = (matchSpec?.preferred || [])
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item) => item.length >= 4);
  const stripEllipsis = (value) => String(value || '').replace(/\\.{2,}$/u, '').trim();
  const compact = (value) => stripEllipsis(value).toLowerCase().replace(/\\s+/g, '');
  const prefixMatches = (text, needle) => {
    if (!text || !needle) return false;
    const hay = stripEllipsis(text).toLowerCase();
    const pin = stripEllipsis(needle).toLowerCase();
    if (!hay || !pin) return false;
    if (hay.startsWith(pin) || pin.startsWith(hay)) return true;
    if (pin.length >= 8 && hay.includes(pin)) return true;
    const hayCompact = compact(text);
    const pinCompact = compact(needle);
    if (!hayCompact || !pinCompact) return false;
    if (hayCompact.startsWith(pinCompact) || pinCompact.startsWith(hayCompact)) return true;
    if (pinCompact.length >= 8 && hayCompact.includes(pinCompact)) return true;
    return false;
  };
  const normalizeExportId = (value) => {
    const text = String(value || '').trim();
    if (!text) return '';
    return text.replace(/^export\\//i, '');
  };
  const idNeedle = normalizeExportId(exportId);
  const feedExportId = (feed) => {
    const direct = feed.getAttribute('data-export-id') || feed.dataset?.exportId || '';
    if (direct) return normalizeExportId(direct);
    const nested = feed.querySelector('[data-export-id], [data-exportid]');
    if (nested) {
      const raw = nested.getAttribute('data-export-id') || nested.getAttribute('data-exportid') || '';
      if (raw) return normalizeExportId(raw);
    }
    return '';
  };
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);

  const scoreFeed = (feed) => {
    const text = (feed.innerText || '').toLowerCase();
    const fid = feedExportId(feed);
    if (idNeedle && fid && fid === idNeedle) {
      return { score: 1000000, requiredHits: required.length, preferredHits: preferred.length, feed };
    }
    let requiredHits = 0;
    for (const needle of required) {
      if (prefixMatches(text, needle)) requiredHits += 1;
    }
    let preferredHits = 0;
    for (const needle of preferred) {
      if (prefixMatches(text, needle)) preferredHits += 1;
    }
    const score = requiredHits * 5000 + preferredHits * 500 + requiredHits * 100 + preferredHits * 10;
    return { score, requiredHits, preferredHits, feed };
  };

  let best = { score: 0, requiredHits: 0, preferredHits: 0, feed: null };
  for (const root of roots) {
    for (const feed of root.querySelectorAll('.comment-feed-wrap')) {
      const result = scoreFeed(feed);
      if (result.score > best.score) best = result;
    }
  }
  if (!best.feed) return { clicked: false };

  const requiredCount = required.length;
  const ok =
    best.score >= 1000000 ||
    (requiredCount > 0 && best.requiredHits === requiredCount);
  if (!ok) {
    return {
      clicked: false,
      bestScore: best.score,
      requiredHits: best.requiredHits,
      requiredCount,
      preview: (best.feed.innerText || '').slice(0, 120),
    };
  }

  best.feed.scrollIntoView({ block: 'center', behavior: 'instant' });
  best.feed.click();
  return {
    clicked: true,
    score: best.score,
    requiredHits: best.requiredHits,
    preferredHits: best.preferredHits,
    preview: (best.feed.innerText || '').slice(0, 120),
  };
}
"""

VERIFY_ACTIVE_FEED_JS = """
([matchSpec, exportId]) => {
  const required = (matchSpec?.required || [])
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item) => item.length >= 4);
  const stripEllipsis = (value) => String(value || '').replace(/\\.{2,}$/u, '').trim();
  const compact = (value) => stripEllipsis(value).toLowerCase().replace(/\\s+/g, '');
  const prefixMatches = (text, needle) => {
    if (!text || !needle) return false;
    const hay = stripEllipsis(text).toLowerCase();
    const pin = stripEllipsis(needle).toLowerCase();
    if (!hay || !pin) return false;
    if (hay.startsWith(pin) || pin.startsWith(hay)) return true;
    if (pin.length >= 8 && hay.includes(pin)) return true;
    const hayCompact = compact(text);
    const pinCompact = compact(needle);
    if (!hayCompact || !pinCompact) return false;
    if (hayCompact.startsWith(pinCompact) || pinCompact.startsWith(hayCompact)) return true;
    if (pinCompact.length >= 8 && hayCompact.includes(pinCompact)) return true;
    return false;
  };
  const normalizeExportId = (value) => {
    const text = String(value || '').trim();
    if (!text) return '';
    return text.replace(/^export\\//i, '');
  };
  const idNeedle = normalizeExportId(exportId);
  const feedExportId = (feed) => {
    const direct = feed.getAttribute('data-export-id') || feed.dataset?.exportId || '';
    if (direct) return normalizeExportId(direct);
    const nested = feed.querySelector('[data-export-id], [data-exportid]');
    if (nested) {
      const raw = nested.getAttribute('data-export-id') || nested.getAttribute('data-exportid') || '';
      if (raw) return normalizeExportId(raw);
    }
    return '';
  };
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const active = root.querySelector('.comment-feed-wrap.active-feed');
    if (!active) continue;
    const fid = feedExportId(active);
    if (idNeedle && fid && fid === idNeedle) {
      return { matched: true, mode: 'export_id', text: (active.innerText || '').slice(0, 120) };
    }
    const text = (active.innerText || '').toLowerCase();
    if (!required.length) continue;
    const hits = required.filter((needle) => prefixMatches(text, needle)).length;
    if (hits === required.length) {
      return { matched: true, mode: 'required_prefix', hits, text: (active.innerText || '').slice(0, 120) };
    }
  }
  return { matched: false };
}
"""

LIST_SIDEBAR_FEEDS_JS = """
() => {
  const normalizeExportId = (value) => {
    const text = String(value || '').trim();
    if (!text) return '';
    return text.replace(/^export\\//i, '');
  };
  const feedExportId = (feed) => {
    const direct = feed.getAttribute('data-export-id') || feed.dataset?.exportId || '';
    if (direct) return normalizeExportId(direct);
    const nested = feed.querySelector('[data-export-id], [data-exportid]');
    if (nested) {
      const raw = nested.getAttribute('data-export-id') || nested.getAttribute('data-exportid') || '';
      if (raw) return normalizeExportId(raw);
    }
    return '';
  };
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  const feeds = [];
  for (const root of roots) {
    for (const feed of root.querySelectorAll('.comment-feed-wrap')) {
      feeds.push({
        text: (feed.innerText || '').slice(0, 120),
        exportId: feedExportId(feed),
        active: String(feed.className || '').includes('active-feed'),
      });
      if (feeds.length >= 8) return feeds;
    }
  }
  return feeds;
}
"""

READ_ACTIVE_FEED_TEXT_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const active = root.querySelector('.comment-feed-wrap.active-feed');
    if (active) return (active.innerText || '').slice(0, 160);
  }
  return '';
}
"""

SCROLL_COMMENT_PANEL_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const selector of [
      '.comment-list',
      '.comment-list-wrap',
      '.comment-panel',
      '[class*="comment-list"]',
      '[class*="comment-panel"]',
    ]) {
      const list = root.querySelector(selector);
      if (list && list.scrollHeight > list.clientHeight + 20) {
        list.scrollTop += Math.max(240, Math.floor(list.clientHeight * 0.75));
        return { scrolled: true, mode: 'container' };
      }
    }
    const items = [...root.querySelectorAll('.comment-item, .comment-list-item, [class*="comment-item"]')];
    if (items.length) {
      items[items.length - 1].scrollIntoView({ block: 'end' });
      return { scrolled: true, mode: 'last_item' };
    }
  }
  return { scrolled: false };
}
"""

COMMENT_CONTENT_VISIBLE_JS = """
(textNeedle) => {
  const needle = String(textNeedle || '').trim();
  if (!needle) return false;
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const el of root.querySelectorAll('.comment-item, .comment-list-item, [class*="comment-item"]')) {
      if (el.closest('.author-comment-input, .comment-create-wrap')) continue;
      const text = (el.innerText || '').trim();
      if (text.includes(needle)) return true;
    }
  }
  return false;
}
"""

CLICK_REPLY_FOR_COMMENT_JS = """
([commentId, contentNeedle]) => {
  const idNeedle = String(commentId || '').trim();
  const textNeedle = String(contentNeedle || '').trim().slice(0, 40);
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  const tryClickReply = (scope) => {
    const items = scope.querySelectorAll('.comment-item, .comment-list-item, [class*="comment-item"]');
    for (const item of items) {
      const text = (item.innerText || '').trim();
      if (idNeedle && item.dataset && item.dataset.commentId === idNeedle) {
        for (const btn of item.querySelectorAll('button, span, a, div')) {
          if ((btn.innerText || '').trim() === '回复') {
            btn.click();
            return { clicked: true, mode: 'id' };
          }
        }
      }
      if (textNeedle && text.includes(textNeedle)) {
        for (const btn of item.querySelectorAll('button, span, a, div')) {
          if ((btn.innerText || '').trim() === '回复') {
            btn.click();
            return { clicked: true, mode: 'text' };
          }
        }
      }
    }
    for (const btn of scope.querySelectorAll('button, span, a, div')) {
      const label = (btn.innerText || '').trim();
      if (label !== '回复') continue;
      const parent = btn.closest('.comment-item, .comment-list-item, [class*="comment"]');
      if (!parent) continue;
      const text = (parent.innerText || '').trim();
      if ((idNeedle && parent.dataset && parent.dataset.commentId === idNeedle) || (textNeedle && text.includes(textNeedle))) {
        btn.click();
        return { clicked: true, mode: 'parent' };
      }
    }
    return null;
  };
  for (const root of roots) {
    const hit = tryClickReply(root);
    if (hit) return hit;
  }
  return { clicked: false };
}
"""

CLICK_REPLY_SUBMIT_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const scope of root.querySelectorAll('.comment-create-wrap, .reply-to-comment, .reply-wrap')) {
      for (const el of scope.querySelectorAll('.tag-wrap.primary .tag-inner, button')) {
        const text = (el.innerText || '').trim();
        if (text === '发表' && !el.closest('.tag-wrap')?.classList?.contains('disabled')) {
          el.click();
          return true;
        }
      }
    }
    for (const el of root.querySelectorAll('textarea.create-input')) {
      const wrap = el.closest('.comment-create-wrap, .reply-to-comment, .reply-wrap');
      if (!wrap) continue;
      for (const btn of wrap.querySelectorAll('.tag-wrap.primary .tag-inner, button.weui-desktop-btn_primary')) {
        const text = (btn.innerText || '').trim();
        if (text === '发表') {
          btn.click();
          return true;
        }
      }
    }
  }
  return false;
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


def _author_already_replied(level_two: list[Any], account_nickname: str | None) -> bool:
    account_name = (account_nickname or "").strip()
    for item in level_two or []:
        if not isinstance(item, dict):
            continue
        nickname = str(item.get("commentNickname") or item.get("nickname") or "").strip()
        if account_name and nickname == account_name:
            return True
    return False


def parse_wechat_comment_list_payload(
    payload: dict[str, Any],
    *,
    export_id: str,
    post_title: str | None,
    account_nickname: str | None,
) -> list[InboundComment]:
    if not payload or payload.get("errCode") not in (None, 0):
        return []
    data = payload.get("data") or {}
    rows = data.get("comment") or data.get("comments") or []
    results: list[InboundComment] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        comment_id = str(item.get("commentId") or item.get("comment_id") or "").strip()
        if not comment_id:
            continue
        content = str(item.get("commentContent") or item.get("content") or "").strip()
        results.append(
            InboundComment(
                platform_post_id=export_id,
                platform_comment_id=comment_id,
                author_name=str(item.get("commentNickname") or "").strip() or None,
                content=content,
                commented_at=_parse_comment_time(item.get("commentCreatetime")),
                post_title=post_title,
                author_username=str(item.get("username") or "").strip() or None,
                already_replied_by_author=_author_already_replied(
                    item.get("levelTwoComment") or [],
                    account_nickname,
                ),
            )
        )
    return results


def fetch_wechat_post_rows(page: Page, *, limit: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_num = 1
    page_size = min(20, limit)
    while len(rows) < limit and page_num <= 5:
        payload = page.evaluate(_FETCH_POST_LIST_JS, [page_num, page_size])
        batch = parse_wechat_post_list_payload(payload) if isinstance(payload, dict) else []
        if not batch:
            break
        rows.extend(batch)
        data = (payload or {}).get("data") or {}
        if not data.get("continueFlag") or len(batch) < page_size:
            break
        page_num += 1
        time.sleep(0.3)
    return rows[:limit]


def fetch_wechat_comments_for_post(
    page: Page,
    *,
    export_id: str,
    post_title: str | None,
    account_nickname: str | None,
) -> list[InboundComment]:
    export_id = normalize_wechat_export_id(export_id)
    results: list[InboundComment] = []
    seen_ids: set[str] = set()
    last_buff = ""
    for _page in range(10):
        payload = page.evaluate(_FETCH_COMMENT_LIST_JS, [export_id, last_buff])
        if not isinstance(payload, dict):
            break
        batch = parse_wechat_comment_list_payload(
            payload,
            export_id=export_id,
            post_title=post_title,
            account_nickname=account_nickname,
        )
        for item in batch:
            if item.platform_comment_id in seen_ids:
                continue
            seen_ids.add(item.platform_comment_id)
            results.append(item)
        data = payload.get("data") or {}
        next_buff = str(data.get("lastBuff") or data.get("last_buff") or "").strip()
        if not batch or not next_buff or next_buff == last_buff:
            break
        last_buff = next_buff
        time.sleep(0.2)
    return results


def normalize_wechat_export_id(export_id: str) -> str:
    text = str(export_id or "").strip()
    if not text:
        return ""
    if text.startswith("export/"):
        return text
    return f"export/{text}"


def _export_id_matches(left: str, right: str) -> bool:
    left_norm = normalize_wechat_export_id(left)
    right_norm = normalize_wechat_export_id(right)
    if not left_norm or not right_norm:
        return False
    return left_norm == right_norm


def lookup_wechat_post_title(page: Page, export_id: str, *, max_pages: int = 30) -> str:
    target = normalize_wechat_export_id(export_id)
    for page_num in range(1, max_pages + 1):
        payload = page.evaluate(_FETCH_POST_LIST_JS, [page_num, 20])
        rows = parse_wechat_post_list_payload(payload) if isinstance(payload, dict) else []
        for row in rows:
            row_id = str(row.get("export_id") or "")
            if _export_id_matches(row_id, target):
                return str(row.get("title") or "").strip()
        data = (payload or {}).get("data") or {} if isinstance(payload, dict) else {}
        if not data.get("continueFlag"):
            break
        time.sleep(0.2)
    return ""


def _wait_for_audience_comments_in_dom(page: Page, *, timeout_ms: int = 15000) -> bool:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            count = page.evaluate(_COUNT_AUDIENCE_COMMENTS_JS)
            if int(count or 0) > 0:
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def _wait_for_comment_content_in_dom(page: Page, content: str, *, timeout_ms: int = 12000) -> bool:
    needle = str(content or "").strip()[:40]
    if not needle:
        return False
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            if page.evaluate(COMMENT_CONTENT_VISIBLE_JS, needle):
                return True
        except Exception:
            pass
        page.evaluate(SCROLL_COMMENT_PANEL_JS)
        page.wait_for_timeout(500)
    return False


def _active_feed_matches(page: Page, *, export_id: str, match_spec: dict[str, list[str]]) -> bool:
    try:
        result = page.evaluate(VERIFY_ACTIVE_FEED_JS, [match_spec, export_id])
    except Exception:
        return False
    return bool(isinstance(result, dict) and result.get("matched"))


def _wait_for_active_feed_matches(
    page: Page,
    *,
    export_id: str,
    match_spec: dict[str, list[str]],
    timeout_ms: int = 8000,
) -> bool:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if _active_feed_matches(page, export_id=export_id, match_spec=match_spec):
            return True
        page.wait_for_timeout(400)
    return False


def extract_wechat_copy_lines(
    description: str | None,
    *,
    main_line1: str | None = None,
    main_line2: str | None = None,
    sub_title: str | None = None,
    sub_title2: str | None = None,
) -> dict[str, str]:
    """Merge video draft copy fields with publish description."""
    parsed = {
        "main_line1": str(main_line1 or "").strip(),
        "main_line2": str(main_line2 or "").strip(),
        "sub_title": str(sub_title or "").strip(),
        "sub_title2": str(sub_title2 or "").strip(),
    }
    lines = [
        line.strip()
        for line in str(description or "").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    non_summary_lines = [
        line
        for line in lines
        if not (line.startswith("小牛说：") or line.startswith("小牛说:"))
    ]
    for line in lines:
        if line.startswith("网友：") or line.startswith("网友:"):
            parsed["main_line2"] = parsed["main_line2"] or line

    # build_wechat_description order: sub_title, main_line2, sub_title2, summary
    if not parsed["sub_title"] and non_summary_lines:
        parsed["sub_title"] = non_summary_lines[0]
    if not parsed["main_line2"] and len(non_summary_lines) >= 2:
        second = non_summary_lines[1]
        if second.startswith("网友"):
            parsed["main_line2"] = second
    if not parsed["sub_title2"] and len(non_summary_lines) >= 2:
        second = non_summary_lines[1]
        if not second.startswith("#") and not second.startswith("网友"):
            parsed["sub_title2"] = parsed["sub_title2"] or second
    if not parsed["sub_title2"] and len(non_summary_lines) >= 3:
        third = non_summary_lines[2]
        if not third.startswith("#"):
            parsed["sub_title2"] = third

    return parsed


def build_wechat_feed_match_spec(
    description: str | None,
    title: str | None = None,
    *,
    main_line1: str | None = None,
    main_line2: str | None = None,
    sub_title: str | None = None,
    sub_title2: str | None = None,
) -> dict[str, list[str]]:
    """Build sidebar match spec from text actually shown in comment-hub feed list."""
    copy = extract_wechat_copy_lines(
        description,
        main_line1=main_line1,
        main_line2=main_line2,
        sub_title=sub_title,
        sub_title2=sub_title2,
    )
    required: list[str] = []
    preferred: list[str] = []

    # Sidebar shows sub_title first, then 网友行 / sub_title2 — not publish main_line1.
    discriminator = copy["sub_title"] or copy["main_line2"] or copy["sub_title2"]
    if discriminator:
        required.append(discriminator)
    elif copy["main_line1"]:
        required.append(copy["main_line1"])

    if copy["main_line1"] and copy["main_line1"] not in required:
        preferred.append(copy["main_line1"])
    if copy["sub_title2"]:
        preferred.append(copy["sub_title2"])
    if copy["sub_title"] and copy["sub_title"] not in required:
        preferred.append(copy["sub_title"])
    if copy["main_line1"] and discriminator:
        preferred.append(f"{copy['main_line1']} {discriminator}".strip())

    if not required:
        title_text = str(title or "").strip()
        if len(title_text) >= 6:
            required.append(title_text)

    return {
        "required": [item for item in dict.fromkeys(required) if len(item) >= 4],
        "preferred": [item for item in dict.fromkeys(preferred) if len(item) >= 4],
    }


def build_wechat_comment_hub_needles(
    description: str | None,
    title: str | None,
    *,
    main_line1: str | None = None,
    main_line2: str | None = None,
    sub_title: str | None = None,
    sub_title2: str | None = None,
) -> list[str]:
    spec = build_wechat_feed_match_spec(
        description,
        title,
        main_line1=main_line1,
        main_line2=main_line2,
        sub_title=sub_title,
        sub_title2=sub_title2,
    )
    return spec["required"] + spec["preferred"]


def _strip_sidebar_ellipsis(value: str) -> str:
    return str(value or "").replace("...", "").replace("…", "").strip()


def needle_matches_sidebar_text(hay: str, needle: str) -> bool:
    """Mirror comment-hub sidebar prefix matching (Python side for tests / fallbacks)."""
    hay_text = _strip_sidebar_ellipsis(hay).lower()
    pin = _strip_sidebar_ellipsis(needle).lower()
    if not hay_text or not pin:
        return False
    if hay_text.startswith(pin) or pin.startswith(hay_text):
        return True
    if len(pin) >= 8 and pin in hay_text:
        return True
    hay_compact = hay_text.replace(" ", "")
    pin_compact = pin.replace(" ", "")
    if not hay_compact or not pin_compact:
        return False
    if hay_compact.startswith(pin_compact) or pin_compact.startswith(hay_compact):
        return True
    return len(pin_compact) >= 8 and pin_compact in hay_compact


def sidebar_text_matches_spec(text: str, match_spec: dict[str, list[str]]) -> bool:
    required = [str(item).strip() for item in (match_spec.get("required") or []) if str(item).strip()]
    if not required:
        return False
    return all(needle_matches_sidebar_text(text, needle) for needle in required)


def _read_active_feed_text(page: Page) -> str:
    try:
        return str(page.evaluate(READ_ACTIVE_FEED_TEXT_JS) or "").strip()
    except Exception:
        return ""


def _wait_for_wujie_comment_hub(page: Page, *, timeout_ms: int = 30000) -> bool:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            if page.evaluate(_WAIT_WUJIE_COMMENT_HUB_JS):
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def _switch_feed_via_api(page: Page, export_id: str) -> bool:
    export_id = normalize_wechat_export_id(export_id)
    if not export_id:
        return False
    activated = page.evaluate(_UPDATE_FEED_COMMENT_JS, export_id)
    if isinstance(activated, dict) and activated.get("errCode") in (None, 0, "0"):
        return True
    logger.warning("update_feed_comment failed for {}: {}", export_id, activated)
    return False


def _select_feed_by_match_spec(page: Page, *, export_id: str, match_spec: dict[str, list[str]]) -> bool:
    if not _wait_for_wujie_comment_hub(page):
        return False
    export_id = normalize_wechat_export_id(export_id)
    if not match_spec.get("required") and not match_spec.get("preferred"):
        return False

    for _attempt in range(15):
        clicked = page.evaluate(SCORE_AND_CLICK_BEST_FEED_JS, [match_spec, export_id])
        if isinstance(clicked, dict) and clicked.get("clicked"):
            human_pause(page, "after_click")
            page.wait_for_timeout(1500)
            if _wait_for_active_feed_matches(
                page, export_id=export_id, match_spec=match_spec, timeout_ms=4000
            ):
                logger.info(
                    "评论中心侧栏已选中作品 score={} required={}/{} preview={} export_id={}",
                    clicked.get("score"),
                    clicked.get("requiredHits"),
                    len(match_spec.get("required") or []),
                    clicked.get("preview"),
                    export_id,
                )
                return True
            logger.warning(
                "点击后 active-feed 校验失败 preview={} export_id={}",
                clicked.get("preview"),
                export_id,
            )
        elif isinstance(clicked, dict) and clicked.get("preview"):
            logger.debug(
                "侧栏暂无足够匹配 score={} required={}/{} preview={}",
                clicked.get("bestScore"),
                clicked.get("requiredHits"),
                clicked.get("requiredCount"),
                clicked.get("preview"),
            )
        page.evaluate(SCROLL_COMMENT_FEED_LIST_JS)
        page.wait_for_timeout(900)
    try:
        feeds = page.evaluate(LIST_SIDEBAR_FEEDS_JS)
    except Exception:
        feeds = []
    logger.warning(
        "侧栏滚动后仍无匹配 export_id={} feeds={}",
        export_id,
        feeds,
    )
    return False


def capture_wechat_hub_feed_text(
    page: Page,
    export_id: str,
    *,
    feed_match_spec: dict[str, list[str]] | None = None,
) -> str:
    """Read comment-hub sidebar text; opens hub and falls back to sidebar click."""
    export_id = normalize_wechat_export_id(export_id)
    if not export_id:
        return ""

    _navigate_comment_hub(page)
    page.wait_for_timeout(2500)
    dismiss_overlays(page)
    if not _wait_for_wujie_comment_hub(page):
        logger.warning("comment hub not ready for hub_feed_text export_id={}", export_id)
        return ""

    _switch_feed_via_api(page, export_id)
    page.wait_for_timeout(1500)
    try:
        text = _read_active_feed_text(page)
    except Exception:
        text = ""
    if text:
        return text

    if feed_match_spec and _select_feed_by_match_spec(
        page,
        export_id=export_id,
        match_spec=feed_match_spec,
    ):
        page.wait_for_timeout(1000)
        try:
            return str(page.evaluate(READ_ACTIVE_FEED_TEXT_JS) or "").strip()
        except Exception:
            return ""
    return ""


def _export_id_active_match(page: Page, export_id: str) -> bool:
    return _active_feed_matches(
        page,
        export_id=export_id,
        match_spec={"required": [], "preferred": []},
    )


def _feed_activation_succeeded(
    page: Page,
    *,
    export_id: str,
    match_spec: dict[str, list[str]],
    comment_content: str | None,
) -> bool:
    if comment_content and _wait_for_comment_content_in_dom(page, comment_content, timeout_ms=12000):
        return _active_feed_matches(page, export_id=export_id, match_spec=match_spec) or _export_id_active_match(
            page, export_id
        )
    if _wait_for_audience_comments_in_dom(page, timeout_ms=10000):
        return _active_feed_matches(page, export_id=export_id, match_spec=match_spec) or _export_id_active_match(
            page, export_id
        )
    if _export_id_active_match(page, export_id):
        page.evaluate(_FETCH_COMMENT_LIST_JS, [export_id, ""])
        page.wait_for_timeout(2000)
        if comment_content and _wait_for_comment_content_in_dom(page, comment_content, timeout_ms=8000):
            return True
        return _wait_for_audience_comments_in_dom(page, timeout_ms=6000)
    return False


def _ensure_feed_active(
    page: Page,
    *,
    export_id: str,
    title: str,
    post_description: str | None = None,
    comment_content: str | None = None,
    main_line1: str | None = None,
    main_line2: str | None = None,
    sub_title: str | None = None,
    sub_title2: str | None = None,
    feed_match_spec: dict[str, list[str]] | None = None,
) -> bool:
    export_id = normalize_wechat_export_id(export_id)
    if not export_id:
        return False

    match_spec = feed_match_spec or build_wechat_feed_match_spec(
        post_description,
        title,
        main_line1=main_line1,
        main_line2=main_line2,
        sub_title=sub_title,
        sub_title2=sub_title2,
    )
    if not match_spec["required"]:
        title_text = str(title or "").strip()
        if len(title_text) >= 4:
            match_spec = {
                "required": [title_text],
                "preferred": list(match_spec.get("preferred") or []),
            }
        else:
            match_spec = {"required": [], "preferred": list(match_spec.get("preferred") or [])}

    for attempt in range(2):
        if not _wait_for_wujie_comment_hub(page):
            logger.warning("评论中心 wujie 未就绪")
            if attempt == 0:
                dismiss_overlays(page)
                page.wait_for_timeout(1500)
                continue
            return False

        logger.info(
            "评论中心匹配规则 export_id={} required={} preferred={} active_before={} attempt={}",
            export_id,
            match_spec["required"],
            match_spec["preferred"][:2],
            page.evaluate(READ_ACTIVE_FEED_TEXT_JS),
            attempt + 1,
        )

        _switch_feed_via_api(page, export_id)
        page.wait_for_timeout(1500)
        active_text = _read_active_feed_text(page)
        if active_text and (
            not match_spec["required"]
            or sidebar_text_matches_spec(active_text, match_spec)
            or _export_id_active_match(page, export_id)
        ):
            page.evaluate(_FETCH_COMMENT_LIST_JS, [export_id, ""])
            page.wait_for_timeout(2500)
            if _feed_activation_succeeded(
                page,
                export_id=export_id,
                match_spec=match_spec,
                comment_content=comment_content,
            ):
                return True

        if match_spec["required"] and _select_feed_by_match_spec(
            page, export_id=export_id, match_spec=match_spec
        ):
            _switch_feed_via_api(page, export_id)
            page.evaluate(_FETCH_COMMENT_LIST_JS, [export_id, ""])
            page.wait_for_timeout(2500)
            if _feed_activation_succeeded(
                page,
                export_id=export_id,
                match_spec=match_spec,
                comment_content=comment_content,
            ):
                return True

        if not match_spec["required"] and _export_id_active_match(page, export_id):
            page.evaluate(_FETCH_COMMENT_LIST_JS, [export_id, ""])
            page.wait_for_timeout(2500)
            if _feed_activation_succeeded(
                page,
                export_id=export_id,
                match_spec=match_spec,
                comment_content=comment_content,
            ):
                return True

        if attempt == 0:
            logger.warning(
                "作品激活第 1 次失败，重试 export_id={} required={}",
                export_id,
                match_spec["required"],
            )
            dismiss_overlays(page)
            page.wait_for_timeout(1200)
            continue

        logger.warning(
            "作品已选中但评论列表未渲染 export_id={} active_feed={}",
            export_id,
            page.evaluate(VERIFY_ACTIVE_FEED_JS, [match_spec, export_id]),
        )
        return False

    return False


def _click_reply_for_comment(
    page: Page,
    *,
    platform_comment_id: str,
    comment_content: str,
) -> dict[str, Any]:
    for _attempt in range(10):
        clicked = page.evaluate(
            CLICK_REPLY_FOR_COMMENT_JS,
            [platform_comment_id, comment_content[:40]],
        )
        if isinstance(clicked, dict) and clicked.get("clicked"):
            return clicked
        page.evaluate(SCROLL_COMMENT_PANEL_JS)
        page.wait_for_timeout(800)
    return {"clicked": False}


def _find_reply_input(page: Page):
    for selector in (
        'textarea.create-input[placeholder*="回复"]',
        "textarea.create-input",
        'textarea[placeholder*="回复"]',
    ):
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=1500):
                return loc.first
        except Exception:
            continue
    return None


def reset_wechat_comment_reply_ui(page: Page) -> None:
    """Close any open reply panel and refresh comment list visibility."""
    _dismiss_wechat_tip(page)
    dismiss_overlays(page)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(500)
    try:
        page.evaluate(
            """
            () => {
              const roots = [document];
              const wujie = document.querySelector('wujie-app');
              if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
              for (const root of roots) {
                for (const wrap of root.querySelectorAll('.comment-create-wrap, .reply-to-comment, .reply-wrap')) {
                  const close = wrap.querySelector('.close, .weui-desktop-icon-close, [class*="close"]');
                  if (close) close.click();
                }
              }
            }
            """
        )
    except Exception:
        pass
    page.evaluate(SCROLL_COMMENT_PANEL_JS)
    page.wait_for_timeout(600)


def activate_wechat_post_session(
    page: Page,
    *,
    post_row: dict[str, Any],
    feed_match_spec: dict[str, list[str]] | None = None,
    post_description: str | None = None,
    main_line1: str | None = None,
    main_line2: str | None = None,
    sub_title: str | None = None,
    sub_title2: str | None = None,
    post_context_json: str | None = None,
    skip_hub_navigate: bool = False,
    comment_content: str | None = None,
) -> PostCommentSession:
    export_id = normalize_wechat_export_id(str(post_row.get("export_id") or "").strip())
    post_title = str(post_row.get("title") or "").strip()
    hub_feed_text = str(post_row.get("hub_feed_text") or "").strip() or None

    if not skip_hub_navigate:
        _navigate_comment_hub(page)
        page.wait_for_timeout(2500)
        dismiss_overlays(page)

    feed_active = _ensure_feed_active(
        page,
        export_id=export_id,
        title=post_title,
        post_description=post_description,
        comment_content=comment_content,
        main_line1=main_line1,
        main_line2=main_line2,
        sub_title=sub_title,
        sub_title2=sub_title2,
        feed_match_spec=feed_match_spec,
    )
    if feed_active:
        try:
            active_text = _read_active_feed_text(page)
        except Exception:
            active_text = ""
        if active_text:
            hub_feed_text = active_text

    return PostCommentSession(
        platform_post_id=export_id,
        post_title=post_title or None,
        hub_feed_text=hub_feed_text,
        feed_match_spec=feed_match_spec,
        feed_active=feed_active,
        post_context_json=post_context_json,
    )


def reply_wechat_audience_comment_on_active_feed(
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

    reset_wechat_comment_reply_ui(page)
    page.wait_for_timeout(800)
    clicked = _click_reply_for_comment(
        page,
        platform_comment_id=comment.platform_comment_id,
        comment_content=comment.content,
    )
    if not clicked.get("clicked"):
        reset_wechat_comment_reply_ui(page)
        page.wait_for_timeout(1000)
        clicked = _click_reply_for_comment(
            page,
            platform_comment_id=comment.platform_comment_id,
            comment_content=comment.content,
        )
    if not clicked.get("clicked"):
        return CommentResult(success=False, error_message="reply_button_not_found")

    human_pause(page, "after_click")
    _dismiss_wechat_tip(page)
    reply_input = _find_reply_input(page)
    if reply_input is None:
        return CommentResult(success=False, error_message="reply_input_not_found")

    try:
        human_fill(page, reply_input, cleaned)
    except Exception as exc:
        return CommentResult(success=False, error_message=f"fill_failed:{exc}")

    human_pause(page, "after_type")
    submit = page.locator('.comment-create-wrap .tag-wrap.primary .tag-inner, .reply-wrap .tag-wrap.primary .tag-inner').first
    try:
        if submit.count() > 0 and submit.is_visible(timeout=1000):
            human_click(page, submit, timeout_ms=8000)
        elif not page.evaluate(CLICK_REPLY_SUBMIT_JS):
            return CommentResult(success=False, error_message="submit_button_not_found")
    except Exception as exc:
        return CommentResult(success=False, error_message=f"submit_click_failed:{exc}")

    human_pause(page, "after_click")
    logger.info("视频号观众评论回复已提交 comment_id={}", comment.platform_comment_id)
    reset_wechat_comment_reply_ui(page)
    return CommentResult(success=True, comment_id=comment.platform_comment_id)


def reply_wechat_audience_comment(
    page: Page,
    *,
    export_id: str,
    post_title: str,
    platform_comment_id: str,
    comment_content: str,
    reply_text: str,
    post_description: str | None = None,
    main_line1: str | None = None,
    main_line2: str | None = None,
    sub_title: str | None = None,
    sub_title2: str | None = None,
    feed_match_spec: dict[str, list[str]] | None = None,
) -> CommentResult:
    cleaned = (reply_text or "").strip()
    if not cleaned:
        return CommentResult(success=False, error_message="empty_reply_text")

    export_id = normalize_wechat_export_id(export_id)
    session = activate_wechat_post_session(
        page,
        post_row={"export_id": export_id, "title": post_title},
        feed_match_spec=feed_match_spec,
        post_description=post_description,
        main_line1=main_line1,
        main_line2=main_line2,
        sub_title=sub_title,
        sub_title2=sub_title2,
    )
    if not session.feed_active:
        return CommentResult(success=False, error_message="work_not_found")

    return reply_wechat_audience_comment_on_active_feed(
        page,
        session=session,
        comment=InboundComment(
            platform_post_id=export_id,
            platform_comment_id=platform_comment_id,
            author_name="",
            content=comment_content,
            commented_at=None,
        ),
        reply_text=cleaned,
    )


def scan_wechat_account_comments(
    page: Page,
    *,
    account_nickname: str | None,
    max_posts: int,
    match_spec_resolver: Any | None = None,
) -> list[tuple[dict[str, Any], list[InboundComment]]]:
    page.goto(COMMENT_HUB_URL, wait_until="domcontentloaded", timeout=60_000)
    human_pause(page, "page_load")
    dismiss_overlays(page)
    rows = fetch_wechat_post_rows(page, limit=max_posts)
    batches: list[tuple[dict[str, Any], list[InboundComment]]] = []
    for row in rows:
        export_id = normalize_wechat_export_id(str(row.get("export_id") or "").strip())
        if not export_id:
            continue
        if int(row.get("comment_count") or 0) <= 0:
            continue
        title = str(row.get("title") or "").strip()
        feed_match_spec = None
        if match_spec_resolver is not None:
            try:
                feed_match_spec = match_spec_resolver(row)
            except Exception as exc:
                logger.debug("match_spec_resolver failed for {}: {}", export_id, exc)
        hub_feed_text = capture_wechat_hub_feed_text(
            page,
            export_id,
            feed_match_spec=feed_match_spec,
        )
        if hub_feed_text:
            row = {**row, "hub_feed_text": hub_feed_text}
        comments = fetch_wechat_comments_for_post(
            page,
            export_id=export_id,
            post_title=title,
            account_nickname=account_nickname,
        )
        batches.append((row, comments))
        time.sleep(0.3)
    return batches
