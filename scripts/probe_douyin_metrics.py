"""Probe Douyin creator metrics APIs and DOM for debugging."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.human_interaction import create_publish_browser_context, launch_publish_browser
from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

HOME_URL = "https://creator.douyin.com/creator-micro/home"
MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage"


def main() -> None:
    factory = get_session_factory()
    with factory() as session:
        account = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == "douyin", PublisherAccount.status == "active")
            .first()
        )
    if account is None:
        print("No active douyin account")
        return

    session_path = Config.ROOT_DIR / account.session_path
    print(f"account={account.id}")

    temp_state = Config.ROOT_DIR / "data" / "publish" / "_probe_metrics_state.json"
    captured: list[dict] = []
    work_list_body: dict | None = None

    def on_response(response) -> None:
        nonlocal work_list_body
        url = response.url
        if response.status != 200:
            return
        if not any(
            token in url
            for token in ("work_list", "work/list", "item/list", "prefetch", "content/manage", "creator/content", "janus")
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
            "status_code": body.get("status_code") if isinstance(body, dict) else None,
        }
        captured.append(item)
        if "work_list" in url:
            work_list_body = body
            out = Config.ROOT_DIR / "data" / "publish" / "probe_douyin_work_list.json"
            out.write_text(json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")

    temp_state.write_bytes(load_encrypted(session_path))
    playwright = sync_playwright().start()
    browser = launch_publish_browser(playwright, headless=False)
    context = create_publish_browser_context(browser, storage_state=str(temp_state))
    page = context.new_page()
    page.on("response", on_response)

    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2000)
    print("home url:", page.url)

    page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(12_000)
    print("manage url:", page.url)

    text_sample = page.evaluate("() => (document.body.innerText || '').slice(0, 800)")
    Path(Config.ROOT_DIR / "data/publish/probe_douyin_text.txt").write_text(text_sample, encoding="utf-8")
    print("text chars:", len(text_sample))

    print("captured:", len(captured))
    for item in captured:
        print(" -", item)

    if work_list_body is None:
        api_try = page.evaluate(
            """async () => {
          const urls = [
            'https://creator.douyin.com/janus/douyin/creator/pc/work_list?page_size=20&page_num=1&status=1',
            'https://creator.douyin.com/janus/douyin/creator/pc/work_list?page_size=20&page_num=1&status=0',
          ];
          const out = [];
          for (const url of urls) {
            try {
              const resp = await fetch(url, { credentials: 'include' });
              out.push({ url, status: resp.status, text: (await resp.text()).slice(0, 300) });
            } catch (e) {
              out.push({ url, error: String(e) });
            }
          }
          return out;
        }"""
        )
        print("api_try:", json.dumps(api_try, ensure_ascii=False, indent=2))

    browser.close()
    playwright.stop()
    temp_state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
