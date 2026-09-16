"""Probe WeChat 写评论 tab on zero-comment feed."""
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

CLICK_ZERO_FEED_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const feed of root.querySelectorAll('.comment-feed-wrap')) {
      const totalEl = feed.querySelector('.feed-comment-total');
      const count = parseInt((totalEl && totalEl.innerText) || '0', 10);
      if (count === 0) {
        feed.click();
        return { clicked: true, text: (feed.innerText || '').slice(0, 100) };
      }
    }
  }
  return { clicked: false };
}
"""

CLICK_WRITE_COMMENT_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const el of root.querySelectorAll('.tag-wrap, .tag-inner, span, div, button')) {
      const text = (el.innerText || '').trim();
      if (text === '写评论') {
        el.click();
        return { clicked: true, cls: String(el.className || '') };
      }
    }
  }
  return { clicked: false };
}
"""

SCAN_JS = """
() => {
  const out = [];
  const walk = (root) => {
    if (!root) return;
    root.querySelectorAll('textarea, input, [contenteditable="true"]').forEach((el) => {
      const hint = [el.getAttribute('placeholder'), el.getAttribute('data-placeholder'), el.getAttribute('aria-label')].filter(Boolean).join(' ');
      out.push({ tag: el.tagName, hint, cls: String(el.className||'').slice(0,80), visible: !!(el.offsetWidth||el.offsetHeight), text: (el.innerText||'').slice(0,40) });
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
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_write.json"
    temp.write_bytes(load_encrypted(session_path))

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    page = browser.new_context(storage_state=str(temp)).new_page()
    page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)
    feed = page.evaluate(CLICK_ZERO_FEED_JS)
    page.wait_for_timeout(4000)
    write = page.evaluate(CLICK_WRITE_COMMENT_JS)
    page.wait_for_timeout(3000)
    inputs = page.evaluate(SCAN_JS)
    body = page.evaluate("() => (document.body.innerText||'').slice(0, 4000)")

    out = Config.ROOT_DIR / "data/publish/probe_wechat_write_comment.json"
    out.write_text(json.dumps({"feed": feed, "write": write, "inputs": inputs, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out)
    print("write", write)
    print("visible inputs", [i for i in inputs if i["visible"]])
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
