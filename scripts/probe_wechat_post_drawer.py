"""Probe post detail drawer after clicking post-feed-item on list page."""
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

SCAN_JS = """
(titleNeedle) => {
  const out = { inputs: [], buttons: [], panels: [] };
  const walk = (root) => {
    if (!root) return;
    root.querySelectorAll('textarea, input, [contenteditable="true"]').forEach((el) => {
      const hint = [el.getAttribute('placeholder'), el.getAttribute('data-placeholder'), el.getAttribute('aria-label')].filter(Boolean).join(' ');
      out.inputs.push({ tag: el.tagName, hint, cls: String(el.className||'').slice(0,80), visible: !!(el.offsetWidth||el.offsetHeight), text: (el.innerText||'').slice(0,40) });
    });
    root.querySelectorAll('button, [role="button"], a, span').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (/评论|回复|发送|发表/.test(text)) out.buttons.push({ text: text.slice(0,30), cls: String(el.className||'').slice(0,60) });
    });
    root.querySelectorAll('[class*="drawer"], [class*="dialog"], [class*="detail"], [class*="panel"], [class*="modal"]').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (text.length > 20) out.panels.push({ cls: String(el.className||'').slice(0,80), text: text.slice(0,200) });
    });
    if (root.shadowRoot) walk(root.shadowRoot);
    root.querySelectorAll('*').forEach((n) => { if (n.shadowRoot) walk(n.shadowRoot); });
  };
  walk(document);
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) walk(wujie.shadowRoot);
  out.body = (document.body.innerText||'').slice(0, 1500);
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
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_drawer.json"
    temp.write_bytes(load_encrypted(session_path))

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    page = browser.new_context(storage_state=str(temp)).new_page()
    page.goto(POST_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)

    clicked = page.evaluate(
        """
        () => {
          const roots = [document];
          const wujie = document.querySelector('wujie-app');
          if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
          for (const root of roots) {
            const item = root.querySelector('.post-feed-item');
            if (item) {
              item.click();
              return { clicked: true, text: (item.innerText||'').slice(0,100), cls: item.className };
            }
          }
          return { clicked: false };
        }
        """
    )
    page.wait_for_timeout(5000)
    snap1 = page.evaluate(SCAN_JS, "")

    # click comment tab/button in drawer if any
    tab = page.evaluate(
        """
        () => {
          const roots = [document];
          const wujie = document.querySelector('wujie-app');
          if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
          for (const root of roots) {
            for (const el of root.querySelectorAll('button, [role="tab"], .tab, [class*="tab"], span, div')) {
              const text = (el.innerText || '').trim();
              if (text === '评论' || text.startsWith('评论(')) {
                el.click();
                return { clicked: true, text };
              }
            }
          }
          return { clicked: false };
        }
        """
    )
    page.wait_for_timeout(4000)
    snap2 = page.evaluate(SCAN_JS, "")
    snap2["tab"] = tab

    out = Config.ROOT_DIR / "data/publish/probe_wechat_post_drawer.json"
    out.write_text(
        json.dumps({"clicked": clicked, "after_open": snap1, "after_comment_tab": snap2}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("saved", out)
    print("inputs", snap2.get("inputs", []))
    print("buttons", snap2.get("buttons", [])[:10])
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
