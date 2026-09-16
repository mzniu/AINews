"""Probe WeChat Channels creator metrics APIs for debugging."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

POST_LIST_URL = "https://channels.weixin.qq.com/platform/post/list"
CREATE_URL = "https://channels.weixin.qq.com/platform/post/create"


def main() -> None:
    factory = get_session_factory()
    with factory() as session:
        account = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == "wechat_channels", PublisherAccount.status == "active")
            .first()
        )
    if account is None:
        print("No active wechat_channels account")
        return

    session_path = Config.ROOT_DIR / account.session_path
    print(f"account={account.id}")

    temp_state = Config.ROOT_DIR / "data" / "publish" / "_probe_metrics_state.json"
    captured: list[dict] = []
    post_list_body: dict | None = None

    def on_response(response) -> None:
        nonlocal post_list_body
        url = response.url
        if response.status != 200:
            return
        if not any(
            token in url
            for token in ("post", "feed", "finder", "list", "stat", "data", "cgi-bin")
        ):
            return
        try:
            body = response.json()
        except Exception:
            return
        item = {
            "url": url,
            "method": response.request.method,
            "post": response.request.post_data,
            "keys": list(body.keys()) if isinstance(body, dict) else type(body).__name__,
            "errCode": body.get("errCode") if isinstance(body, dict) else None,
            "errcode": body.get("errcode") if isinstance(body, dict) else None,
            "ret": body.get("ret") if isinstance(body, dict) else None,
        }
        captured.append(item)
        if any(token in url for token in ("post/list", "post_list", "get_feed", "feed_list", "finderpost")):
            post_list_body = body
            out = Config.ROOT_DIR / "data" / "publish" / "probe_wechat_post_list.json"
            out.write_text(json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")

    temp_state.write_bytes(load_encrypted(session_path))
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state=str(temp_state))
    page = context.new_page()
    page.on("response", on_response)

    page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2000)
    print("create url:", page.url)

    page.goto(POST_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(10000)
    print("list url:", page.url)

    text_sample = page.evaluate("() => (document.body.innerText || '').slice(0, 600)")
    Path(Config.ROOT_DIR / "data/publish/probe_wechat_text.txt").write_text(text_sample, encoding="utf-8")
    print("text chars:", len(text_sample), "has_login:", "登录" in text_sample)

    print("captured:", len(captured))
    for item in captured[:30]:
        print(" -", item)

    browser.close()
    playwright.stop()
    temp_state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
