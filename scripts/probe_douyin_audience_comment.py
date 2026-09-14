"""Probe Douyin creator audience-comment list + reply UI (research gate).

Usage:
  python scripts/probe_douyin_audience_comment.py
  python scripts/probe_douyin_audience_comment.py --video-id 7673873560674290944
  python scripts/probe_douyin_audience_comment.py --title "关键词"

Writes: data/publish/probe_douyin_audience_comment_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import Page, sync_playwright

from services.publishing.adapters.douyin_comment import (
    _dismiss_overlays,
    _fetch_work_rows,
    _open_comment_page_for_work,
    _pick_work,
)
from services.publishing.human_interaction import create_publish_browser_context, launch_publish_browser
from services.publishing.human_pacing import human_pause
from services.publishing.metrics.adapters.douyin import CONTENT_MANAGE_URL
from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

REPORT_PATH = Config.ROOT_DIR / "data" / "publish" / "probe_douyin_audience_comment_report.json"

COMMENT_API_FRAGMENTS = (
    "/comment/list",
    "/comment/comment",
    "/interactive/comment",
    "/item/comment",
    "list_comment",
    "comment_list",
)

EXTRACT_AUDIENCE_COMMENTS_JS = """
() => {
  const rows = [];
  const seen = new Set();
  const push = (id, author, content, hasReply) => {
    const text = String(content || '').trim();
    const name = String(author || '').trim();
    if (!text || text.length < 2) return;
    const cid = String(id || '').trim() || `hash:${name}:${text.slice(0, 48)}`;
    if (seen.has(cid)) return;
    seen.add(cid);
    rows.push({ comment_id: cid, author_name: name, content: text, has_reply_btn: !!hasReply });
  };
  const selectors = [
    '[class*="comment-item"]',
    '[class*="CommentItem"]',
    '[class*="comment-list"] > div',
    '[data-e2e*="comment"]',
    'li',
  ];
  for (const selector of selectors) {
    for (const el of document.querySelectorAll(selector)) {
      const text = (el.innerText || '').trim();
      if (!text || text.length < 4 || text.length > 500) continue;
      if (/有爱评论|说点好听的|发表评论/.test(text)) continue;
      const hasReply = [...el.querySelectorAll('span, button, a, div')].some(
        (btn) => (btn.innerText || '').trim() === '回复'
      );
      if (!hasReply && !/\\d{1,2}:\\d{2}/.test(text)) continue;
      const authorEl = el.querySelector('[class*="nickname"], [class*="user-name"], [class*="name"]');
      const contentEl = el.querySelector('[class*="content"], [class*="text"], p');
      const author = authorEl ? authorEl.innerText.trim() : '';
      let content = contentEl ? contentEl.innerText.trim() : text.split('\\n').slice(-1)[0].trim();
      const id = el.getAttribute('data-comment-id') || el.dataset?.commentId || '';
      push(id, author, content, hasReply);
      if (rows.length >= 20) return rows;
    }
  }
  return rows;
}
"""


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


def _capture_responses(page: Page, action) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def on_response(response) -> None:
        url = response.url or ""
        if response.status != 200:
            return
        if not any(fragment in url for fragment in COMMENT_API_FRAGMENTS):
            return
        try:
            payload = response.json()
        except Exception:
            return
        if isinstance(payload, dict):
            captured.append({"url": url, "payload": payload})

    page.on("response", on_response)
    try:
        action()
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    return captured


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id")
    parser.add_argument("--video-id")
    parser.add_argument("--title")
    args = parser.parse_args()

    account = _load_account(args.account_id)
    if account is None:
        print("No active douyin account")
        return 1

    session_path = Config.DATA_DIR / "publish" / "sessions" / Path(account.session_path).name
    if not session_path.exists():
        session_path = Path(account.session_path)
    if not session_path.exists():
        print(f"Session not found: {account.session_path}")
        return 1

    report: dict[str, Any] = {
        "probed_at": datetime.utcnow().isoformat(),
        "account_id": account.id,
        "nickname": account.nickname,
    }

    temp_state = Config.DATA_DIR / "publish" / "_douyin_audience_probe_state.json"
    temp_state.write_bytes(load_encrypted(session_path))

    with sync_playwright() as playwright:
        browser = launch_publish_browser(playwright, headless=False)
        context = create_publish_browser_context(browser, storage_state=str(temp_state))
        page = context.new_page()

        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")
        _dismiss_overlays(page)

        rows = _fetch_work_rows(page)
        work = _pick_work(rows, title=args.title or "", video_id=args.video_id)
        if work is None:
            report["error"] = "work_not_found"
            REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            browser.close()
            temp_state.unlink(missing_ok=True)
            return 1

        report["work"] = {
            "video_id": work.get("video_id"),
            "title": work.get("title"),
            "comment_count": work.get("comment_count"),
        }

        captured = _capture_responses(page, lambda: _open_comment_page_for_work(page, work))
        page.wait_for_timeout(3000)
        report["page_url"] = page.url
        report["captured_apis"] = [
            {
                "url": item["url"],
                "keys": list(item["payload"].keys())[:20],
                "status_code": item["payload"].get("status_code") or item["payload"].get("result"),
            }
            for item in captured
        ]
        report["api_payload_samples"] = captured[:3]
        report["dom_comments"] = page.evaluate(EXTRACT_AUDIENCE_COMMENTS_JS)
        report["page_text_snippet"] = (page.inner_text("body") or "")[:2000]

        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()

    temp_state.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
