"""Probe WeChat Channels network responses broadly."""
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


def main() -> None:
    factory = get_session_factory()
    with factory() as session:
        account = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == "wechat_channels", PublisherAccount.status == "active")
            .first()
        )
    session_path = Config.ROOT_DIR / account.session_path
    temp_state = Config.ROOT_DIR / "data/publish/_probe.json"
    temp_state.write_bytes(load_encrypted(session_path))

    captured = []
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(storage_state=str(temp_state))
    page = ctx.new_page()

    def on_response(response):
        url = response.url
        if "channels.weixin.qq.com" not in url and "weixin.qq.com" not in url:
            return
        entry = {"url": url, "status": response.status, "method": response.request.method}
        try:
            body = response.json()
            entry["json_keys"] = list(body.keys()) if isinstance(body, dict) else type(body).__name__
            if isinstance(body, dict) and any(k in body for k in ("list", "feedList", "postList", "data", "items")):
                out = Config.ROOT_DIR / "data/publish/probe_wechat_candidate.json"
                out.write_text(json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            entry["content_type"] = response.headers.get("content-type", "")
        captured.append(entry)

    page.on("response", on_response)
    page.goto(POST_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(12000)

    dom = page.evaluate(
        """() => {
      const roots = [document];
      const wujie = document.querySelector('wujie-app');
      if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
      const rows = [];
      for (const root of roots) {
        root.querySelectorAll('tr, [class*="post"], [class*="feed"], [class*="video"]').forEach((el) => {
          const text = (el.innerText || '').slice(0, 120);
          if (!text.trim()) return;
          rows.push({cls: (el.className||'').toString().slice(0,60), text});
        });
      }
      return {
        title: document.title,
        url: location.href,
        bodyText: (document.body.innerText||'').slice(0,500),
        rowCount: rows.length,
        rows: rows.slice(0, 8),
      };
    }"""
    )

    Path(Config.ROOT_DIR / "data/publish/probe_wechat_all.json").write_text(
        json.dumps({"captured": captured, "dom": dom}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("captured", len(captured))
    for item in captured:
        if item.get("json_keys"):
            print(item["url"][:120], item.get("json_keys"))
    print("dom rows", dom.get("rowCount"))
    browser.close()
    pw.stop()
    temp_state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
