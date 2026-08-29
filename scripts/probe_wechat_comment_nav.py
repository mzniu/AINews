"""One-off probe for WeChat Channels comment navigation paths."""
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

POST_LIST_URL = "https://channels.weixin.qq.com/platform/post/list"

CLICK_FIRST_POST_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const body = root.querySelector('.post-list-body');
    if (!body) continue;
    const candidates = body.querySelectorAll(
      '.post-item, .feed-item, [class*="post-item"], [class*="feed-item"], tr, .title, [class*="title"]'
    );
    for (const el of candidates) {
      const text = (el.innerText || '').trim();
      if (text.length < 8) continue;
      el.click();
      return { clicked: true, text: text.slice(0, 100), cls: String(el.className || '') };
    }
    const text = (body.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
    if (text.length) {
      const first = text.find(t => t.length > 8 && !t.includes('发表视频'));
      if (first) {
        const loc = Array.from(body.querySelectorAll('*')).find(el => (el.innerText || '').trim() === first);
        if (loc) {
          loc.click();
          return { clicked: true, text: first.slice(0, 100), cls: String(loc.className || '') };
        }
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
      const hint = [
        el.getAttribute('placeholder'),
        el.getAttribute('data-placeholder'),
        el.getAttribute('aria-label'),
      ].filter(Boolean).join(' ');
      out.push({
        tag: el.tagName,
        hint,
        cls: String(el.className || '').slice(0, 80),
        visible: !!(el.offsetWidth || el.offsetHeight),
      });
    });
    if (root.shadowRoot) walk(root.shadowRoot);
    root.querySelectorAll('*').forEach((node) => {
      if (node.shadowRoot) walk(node.shadowRoot);
    });
  };
  walk(document);
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) walk(wujie.shadowRoot);
  return out.slice(0, 30);
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
    if account is None:
        print("no account")
        return

    session_path = Config.ROOT_DIR / account.session_path
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_comment.json"
    temp.write_bytes(load_encrypted(session_path))

    captured: list[str] = []
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(storage_state=str(temp))
    page = ctx.new_page()

    def on_response(response) -> None:
        url = response.url.lower()
        if response.status == 200 and any(
            token in url for token in ("comment", "interaction", "post_list", "post/detail")
        ):
            captured.append(response.url)

    page.on("response", on_response)
    page.goto(POST_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)

    clicked = page.evaluate(CLICK_FIRST_POST_JS)
    page.wait_for_timeout(5000)
    after_click = {
        "url": page.url,
        "clicked": clicked,
        "text": page.evaluate("() => (document.body.innerText || '').slice(0, 1000)"),
        "inputs": page.evaluate(SCAN_INPUTS_JS),
    }

    interaction_urls = [
        "https://channels.weixin.qq.com/platform/interaction/comment",
        "https://channels.weixin.qq.com/platform/interaction/index",
        "https://channels.weixin.qq.com/micro/interaction/comment",
        "https://channels.weixin.qq.com/micro/content/post/list",
    ]
    interaction_results = []
    for url in interaction_urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            interaction_results.append(
                {
                    "url": page.url,
                    "text": page.evaluate("() => (document.body.innerText || '').slice(0, 400)"),
                    "inputs": page.evaluate(SCAN_INPUTS_JS),
                }
            )
        except Exception as exc:
            interaction_results.append({"url": url, "error": str(exc)})

    out = Config.ROOT_DIR / "data/publish/probe_wechat_comment_nav.json"
    out.write_text(
        json.dumps(
            {
                "after_click": after_click,
                "interaction_results": interaction_results,
                "captured": captured[:40],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("saved", out)
    print("clicked", clicked)
    print("after url", after_click["url"])
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
