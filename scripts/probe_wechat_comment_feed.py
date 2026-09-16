"""Probe clicking comment feed items on interaction/comment page."""
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

SCAN_JS = """
() => {
  const out = { inputs: [], buttons: [], feeds: [] };
  const walk = (root) => {
    if (!root) return;
    root.querySelectorAll('.comment-feed-wrap, [class*="comment-feed"]').forEach((el) => {
      out.feeds.push({
        cls: String(el.className || ''),
        text: (el.innerText || '').trim().slice(0, 120),
        active: !String(el.className || '').includes('inactive'),
      });
    });
    root.querySelectorAll('textarea, input, [contenteditable="true"]').forEach((el) => {
      const hint = [
        el.getAttribute('placeholder'),
        el.getAttribute('data-placeholder'),
        el.getAttribute('aria-label'),
      ].filter(Boolean).join(' ');
      out.inputs.push({
        tag: el.tagName,
        hint,
        cls: String(el.className || '').slice(0, 80),
        visible: !!(el.offsetWidth || el.offsetHeight),
      });
    });
    root.querySelectorAll('button, [role="button"], a').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (/回复|发送|评论/.test(text)) {
        out.buttons.push({ text: text.slice(0, 30), cls: String(el.className || '').slice(0, 60) });
      }
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
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_feed.json"
    temp.write_bytes(load_encrypted(session_path))

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    page = browser.new_context(storage_state=str(temp)).new_page()
    page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)
    before = page.evaluate(SCAN_JS)

    clicked = page.evaluate(
        """
        () => {
          const roots = [document];
          const wujie = document.querySelector('wujie-app');
          if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
          for (const root of roots) {
            const feeds = root.querySelectorAll('.comment-feed-wrap');
            for (const feed of feeds) {
              feed.click();
              return { clicked: true, cls: feed.className, text: (feed.innerText||'').slice(0,80) };
            }
          }
          return { clicked: false };
        }
        """
    )
    page.wait_for_timeout(4000)
    after1 = page.evaluate(SCAN_JS)
    after1["clicked"] = clicked

    # try reply button
    reply_click = page.evaluate(
        """
        () => {
          const roots = [document];
          const wujie = document.querySelector('wujie-app');
          if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
          for (const root of roots) {
            for (const el of root.querySelectorAll('button, [role="button"], a, span')) {
              const text = (el.innerText || '').trim();
              if (text === '回复' || text.includes('回复')) {
                el.click();
                return { clicked: true, text };
              }
            }
          }
          return { clicked: false };
        }
        """
    )
    page.wait_for_timeout(3000)
    after2 = page.evaluate(SCAN_JS)
    after2["reply_click"] = reply_click

    out = Config.ROOT_DIR / "data/publish/probe_wechat_comment_feed.json"
    out.write_text(
        json.dumps({"before": before, "after_feed_click": after1, "after_reply_click": after2}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("saved", out)
    print("feeds", len(before.get("feeds", [])))
    print("inputs after reply", after2.get("inputs", []))
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
