"""Find submit button on WeChat 写评论 form."""
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

OPEN_WRITE_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const feed = root.querySelector('.comment-feed-wrap');
    if (feed) feed.click();
    for (const el of root.querySelectorAll('.tag-wrap, .tag-inner, span, div, button')) {
      if ((el.innerText || '').trim() === '写评论') { el.click(); return true; }
    }
  }
  return false;
}
"""

SCAN_BUTTONS_JS = """
() => {
  const out = [];
  const walk = (root) => {
    if (!root) return;
    root.querySelectorAll('button, [role="button"], span, a, div').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (/发送|发表|评论|提交/.test(text) && text.length < 12) {
        out.push({ text, cls: String(el.className||'').slice(0,80), visible: !!(el.offsetWidth||el.offsetHeight) });
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
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_btn.json"
    temp.write_bytes(load_encrypted(Config.ROOT_DIR / account.session_path))
    pw = sync_playwright().start()
    page = pw.chromium.launch(headless=False).new_context(storage_state=str(temp)).new_page()
    page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)
    page.evaluate(OPEN_WRITE_JS)
    page.wait_for_timeout(3000)
    buttons = page.evaluate(SCAN_BUTTONS_JS)
    print(json.dumps(buttons, ensure_ascii=False, indent=2))
    page.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
