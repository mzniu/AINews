"""Deep scan WeChat interaction comment page after selecting a feed by title."""
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

DEEP_SCAN_JS = """
() => {
  const hits = [];
  const walk = (root, path = 'document') => {
    if (!root) return;
    root.querySelectorAll('*').forEach((el) => {
      const tag = el.tagName;
      const cls = String(el.className || '');
      const text = (el.innerText || '').trim();
      const hint = [el.getAttribute('placeholder'), el.getAttribute('data-placeholder'), el.getAttribute('aria-label'), el.getAttribute('title')].filter(Boolean).join(' | ');
      const editable = el.getAttribute('contenteditable');
      if (
        tag === 'TEXTAREA' ||
        editable === 'true' ||
        (tag === 'INPUT' && hint) ||
        /comment|reply|回复|评论|说点/.test(hint + ' ' + cls + ' ' + text.slice(0, 40))
      ) {
        hits.push({
          path,
          tag,
          cls: cls.slice(0, 100),
          hint,
          text: text.slice(0, 80),
          visible: !!(el.offsetWidth || el.offsetHeight),
        });
      }
      if (el.shadowRoot) walk(el.shadowRoot, path + '::shadow');
    });
  };
  walk(document);
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) walk(wujie.shadowRoot, 'wujie-app::shadow');
  return hits;
}
"""

CLICK_FEED_BY_TITLE_JS = """
(titleNeedle) => {
  const needle = (titleNeedle || '').trim().toLowerCase();
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const feeds = root.querySelectorAll('.comment-feed-wrap');
    for (const feed of feeds) {
      const text = (feed.innerText || '').toLowerCase();
      if (!needle || text.includes(needle)) {
        feed.click();
        return { clicked: true, text: (feed.innerText || '').slice(0, 120), cls: feed.className };
      }
    }
  }
  return { clicked: false };
}
"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="")
    args = parser.parse_args()

    factory = get_session_factory()
    with factory() as session:
        account = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == "wechat_channels", PublisherAccount.status == "active")
            .first()
        )
    session_path = Config.ROOT_DIR / account.session_path
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_deep.json"
    temp.write_bytes(load_encrypted(session_path))

    comment_apis: list[dict] = []

    def on_response(response) -> None:
        url = response.url
        if "comment" not in url.lower():
            return
        if response.status not in (200, 201):
            return
        try:
            body = response.json()
        except Exception:
            body = None
        comment_apis.append({"url": url, "body_keys": list(body.keys()) if isinstance(body, dict) else None})

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    page = browser.new_context(storage_state=str(temp)).new_page()
    page.on("response", on_response)
    page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)
    clicked = page.evaluate(CLICK_FEED_BY_TITLE_JS, args.title)
    page.wait_for_timeout(4000)
    hits = page.evaluate(DEEP_SCAN_JS)
    body_text = page.evaluate("() => (document.body.innerText || '').slice(0, 2500)")

    out = Config.ROOT_DIR / "data/publish/probe_wechat_comment_deep.json"
    out.write_text(
        json.dumps(
            {
                "clicked": clicked,
                "hits": hits,
                "body_text": body_text,
                "comment_apis": comment_apis[:30],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("saved", out)
    print("clicked", clicked)
    print("hits", len(hits))
    for h in hits[:15]:
        print(h)
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
