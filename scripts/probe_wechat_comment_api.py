"""Capture WeChat Channels comment-related API calls on interaction/comment page."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

COMMENT_URL = "https://channels.weixin.qq.com/platform/interaction/comment"

CLICK_FEED_WITH_COMMENTS_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const feeds = root.querySelectorAll('.comment-feed-wrap');
    for (const feed of feeds) {
      const totalEl = feed.querySelector('.feed-comment-total');
      const count = parseInt((totalEl && totalEl.innerText) || '0', 10);
      if (count > 0) {
        feed.click();
        return { clicked: true, count, text: (feed.innerText || '').slice(0, 120) };
      }
    }
  }
  const first = roots[0].querySelector('.comment-feed-wrap');
  if (first) {
    first.click();
    return { clicked: true, count: 0, text: (first.innerText || '').slice(0, 120) };
  }
  return { clicked: false };
}
"""

CLICK_REPLY_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const el of root.querySelectorAll('button, span, a, div')) {
      const text = (el.innerText || '').trim();
      if (text === '回复' || text.startsWith('回复')) {
        el.click();
        return { clicked: true, text };
      }
    }
  }
  return { clicked: false };
}
"""

SCAN_INPUTS_JS = """
() => {
  const out = [];
  const walk = (root) => {
    if (!root) return;
    root.querySelectorAll('textarea, input, [contenteditable="true"]').forEach((el) => {
      const hint = [el.getAttribute('placeholder'), el.getAttribute('data-placeholder'), el.getAttribute('aria-label')].filter(Boolean).join(' ');
      out.push({ tag: el.tagName, hint, cls: String(el.className||'').slice(0,80), visible: !!(el.offsetWidth||el.offsetHeight) });
    });
    if (root.shadowRoot) walk(root.shadowRoot);
    root.querySelectorAll('*').forEach((n) => { if (n.shadowRoot) walk(n.shadowRoot); });
  };
  walk(document);
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) walk(wujie.shadowRoot);
  return out;
}
"""


def main() -> None:
    factory = get_session_factory()
    with factory() as session:
        account = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == "wechat_channels", PublisherAccount.status == "active")
            .first()
        )
    session_path = Config.ROOT_DIR / account.session_path
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_api.json"
    temp.write_bytes(load_encrypted(session_path))

    api_calls: list[dict] = []

    def on_request(request) -> None:
        url = request.url
        if "mmfinderassistant" not in url and "comment" not in url.lower():
            return
        body = None
        try:
            body = request.post_data_json
        except Exception:
            body = request.post_data
        api_calls.append({"phase": phase, "method": request.method, "url": url, "body": body})

    phase = "load"
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    page = browser.new_context(storage_state=str(temp)).new_page()
    page.on("request", on_request)

    page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)

    phase = "feed_click"
    feed = page.evaluate(CLICK_FEED_WITH_COMMENTS_JS)
    page.wait_for_timeout(5000)
    inputs_after_feed = page.evaluate(SCAN_INPUTS_JS)
    body_after_feed = page.evaluate("() => (document.body.innerText||'').slice(0, 3000)")

    phase = "reply_click"
    reply = page.evaluate(CLICK_REPLY_JS)
    page.wait_for_timeout(4000)
    inputs_after_reply = page.evaluate(SCAN_INPUTS_JS)

    out = Config.ROOT_DIR / "data/publish/probe_wechat_comment_api.json"
    out.write_text(
        json.dumps(
            {
                "feed": feed,
                "reply": reply,
                "inputs_after_feed": inputs_after_feed,
                "inputs_after_reply": inputs_after_reply,
                "body_after_feed": body_after_feed,
                "api_calls": api_calls,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print("saved", out)
    print("feed", feed)
    print("reply", reply)
    print("api count", len(api_calls))
    for call in api_calls:
        if "comment" in call["url"].lower():
            print(call["method"], call["url"].split("mmfinderassistant-bin/")[-1].split("?")[0])
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
