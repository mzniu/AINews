"""Probe WeChat zero-comment feed and comment submit API."""
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

CLICK_ZERO_COMMENT_FEED_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const feeds = root.querySelectorAll('.comment-feed-wrap');
    for (const feed of feeds) {
      const totalEl = feed.querySelector('.feed-comment-total');
      const count = parseInt((totalEl && totalEl.innerText) || '0', 10);
      if (count === 0) {
        feed.click();
        return { clicked: true, count, text: (feed.innerText || '').slice(0, 120) };
      }
    }
  }
  return { clicked: false };
}
"""

SCAN_JS = """
() => {
  const out = { inputs: [], buttons: [], body: '' };
  const walk = (root) => {
    if (!root) return;
    root.querySelectorAll('textarea, input, [contenteditable="true"]').forEach((el) => {
      const hint = [el.getAttribute('placeholder'), el.getAttribute('data-placeholder'), el.getAttribute('aria-label')].filter(Boolean).join(' ');
      out.inputs.push({ tag: el.tagName, hint, cls: String(el.className||'').slice(0,80), visible: !!(el.offsetWidth||el.offsetHeight) });
    });
    root.querySelectorAll('button, span, a, div').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (/回复|发送|发表|评论/.test(text) && text.length < 20) out.buttons.push({ text, cls: String(el.className||'').slice(0,60) });
    });
    if (root.shadowRoot) walk(root.shadowRoot);
    root.querySelectorAll('*').forEach((n) => { if (n.shadowRoot) walk(n.shadowRoot); });
  };
  walk(document);
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) walk(wujie.shadowRoot);
  out.body = (document.body.innerText || '').slice(0, 4000);
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
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_zero.json"
    temp.write_bytes(load_encrypted(session_path))

    api_calls: list[dict] = []

    def on_request(request) -> None:
        url = request.url
        if "comment/" not in url:
            return
        body = None
        try:
            body = request.post_data_json
        except Exception:
            body = request.post_data
        api_calls.append({"url": url, "body": body})

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    page = browser.new_context(storage_state=str(temp)).new_page()
    page.on("request", on_request)
    page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)

    feed = page.evaluate(CLICK_ZERO_COMMENT_FEED_JS)
    page.wait_for_timeout(5000)
    snap = page.evaluate(SCAN_JS)

    out = Config.ROOT_DIR / "data/publish/probe_wechat_zero_comment.json"
    out.write_text(
        json.dumps({"feed": feed, "snap": snap, "api_calls": api_calls}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print("saved", out)
    print("feed", feed)
    print("inputs", [i for i in snap["inputs"] if i["visible"]])
    print("buttons", snap["buttons"][:15])
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
