"""Probe WeChat Channels interaction/comment page for selectors."""
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
  const out = { inputs: [], buttons: [], texts: [], rows: [] };
  const walk = (root, depth = 0) => {
    if (!root || depth > 8) return;
    root.querySelectorAll('textarea, input, [contenteditable="true"]').forEach((el) => {
      const hint = [
        el.getAttribute('placeholder'),
        el.getAttribute('data-placeholder'),
        el.getAttribute('aria-label'),
      ].filter(Boolean).join(' ');
      const text = (el.innerText || '').trim();
      out.inputs.push({
        tag: el.tagName,
        hint,
        text: text.slice(0, 40),
        cls: String(el.className || '').slice(0, 80),
        visible: !!(el.offsetWidth || el.offsetHeight),
      });
    });
    root.querySelectorAll('button, [role="button"]').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (!text) return;
      if (/评论|回复|发送|发表/.test(text)) {
        out.buttons.push({ text: text.slice(0, 40), cls: String(el.className || '').slice(0, 60) });
      }
    });
    root.querySelectorAll('[class*="comment"], [class*="reply"], [class*="interaction"]').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (text && text.length < 120) out.texts.push({ cls: String(el.className || '').slice(0, 60), text });
    });
    root.querySelectorAll('tr, [class*="item"], [class*="row"]').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (text.length > 12 && text.length < 180) {
        out.rows.push({ cls: String(el.className || '').slice(0, 60), text: text.slice(0, 100) });
      }
    });
    if (root.shadowRoot) walk(root.shadowRoot, depth + 1);
    root.querySelectorAll('*').forEach((node) => {
      if (node.shadowRoot) walk(node.shadowRoot, depth + 1);
    });
  };
  walk(document);
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) walk(wujie.shadowRoot, 0);
  out.bodyText = (document.body.innerText || '').slice(0, 1200);
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
    temp = Config.ROOT_DIR / "data/publish/_probe_wx_ic.json"
    temp.write_bytes(load_encrypted(session_path))

    api_hits: list[dict] = []

    def on_response(response) -> None:
        url = response.url
        if response.status not in (200, 201):
            return
        if not any(token in url for token in ("comment", "interaction", "mmfinderassistant")):
            return
        try:
            body = response.json()
        except Exception:
            return
        if isinstance(body, dict) and body.get("errCode") == 0:
            api_hits.append({"url": url, "keys": list(body.keys()), "data_keys": list((body.get("data") or {}).keys())})

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(storage_state=str(temp))
    page = ctx.new_page()
    page.on("response", on_response)

    page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=60_000)
    for wait_ms in (3000, 5000, 8000):
        page.wait_for_timeout(wait_ms)
        snap = page.evaluate(SCAN_JS)
        snap["wait_ms"] = wait_ms
        snap["url"] = page.url
        if any(inp.get("visible") and ("评论" in (inp.get("hint") or "") or inp.get("tag") == "TEXTAREA") for inp in snap["inputs"]):
            break

    # click first visible row if any
    clicked = page.evaluate(
        """
        () => {
          const roots = [document];
          const wujie = document.querySelector('wujie-app');
          if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
          for (const root of roots) {
            const rows = root.querySelectorAll('[class*="comment"], [class*="item"], tr');
            for (const row of rows) {
              const text = (row.innerText || '').trim();
              if (text.length < 12) continue;
              row.click();
              return { clicked: true, text: text.slice(0, 80) };
            }
          }
          return { clicked: false };
        }
        """
    )
    page.wait_for_timeout(4000)
    after_click = page.evaluate(SCAN_JS)
    after_click["clicked"] = clicked
    after_click["url"] = page.url

    out = Config.ROOT_DIR / "data/publish/probe_wechat_interaction_comment.json"
    out.write_text(
        json.dumps(
            {"initial": snap, "after_click": after_click, "api_hits": api_hits[:25]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("saved", out)
    print("inputs", len(after_click.get("inputs", [])))
    print("buttons", after_click.get("buttons", [])[:5])
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
