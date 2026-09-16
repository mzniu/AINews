"""Test WeChat comment submit flow."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.adapters.wechat_channels_comment import (
    _find_wechat_comment_input,
    _navigate_comment_hub,
    _open_write_comment_tab,
)
from services.publishing.human_form import human_fill
from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config


def main() -> None:
    factory = get_session_factory()
    with factory() as session:
        account = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == "wechat_channels", PublisherAccount.status == "active")
            .first()
        )
    temp = Config.ROOT_DIR / "data/publish/_t.json"
    temp.write_bytes(load_encrypted(Config.ROOT_DIR / account.session_path))
    apis: list[dict] = []

    def on_req(req) -> None:
        if "comment/" in req.url and req.method == "POST":
            try:
                body = req.post_data_json
            except Exception:
                body = None
            apis.append({"u": req.url.split("mmfinderassistant-bin/")[-1].split("?")[0], "b": body})

    pw = sync_playwright().start()
    page = pw.chromium.launch(headless=False).new_context(storage_state=str(temp)).new_page()
    page.on("request", on_req)
    _navigate_comment_hub(page)
    page.wait_for_timeout(3000)
    page.evaluate(
        """
        () => {
          const roots=[document];
          const w=document.querySelector('wujie-app');
          if(w&&w.shadowRoot)roots.push(w.shadowRoot);
          for(const r of roots){
            for(const feed of r.querySelectorAll('.comment-feed-wrap')){
              const c=parseInt(feed.querySelector('.feed-comment-total')?.innerText||'0',10);
              if(c===0){ feed.click(); return; }
            }
          }
        }
        """
    )
    page.wait_for_timeout(2500)
    _open_write_comment_tab(page)
    page.wait_for_timeout(1500)
    tip = page.get_by_role("button", name="我知道了")
    if tip.count():
        tip.first.click(timeout=3000)
        print("dismissed tip")
    page.wait_for_timeout(500)
    inp = _find_wechat_comment_input(page)
    human_fill(page, inp, "你觉得这条资讯最关键的点是什么？")
    page.wait_for_timeout(1000)
    pub = page.get_by_role("button", name="发表")
    print("发表 count", pub.count())
    if pub.count():
        pub.first.click()
        page.wait_for_timeout(4000)
    print(json.dumps(apis, ensure_ascii=False, indent=2)[:2000])
    page.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
