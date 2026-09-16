"""Compare WeChat Channels statistic/post vs post/list metrics APIs."""
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

STAT_URL = "https://channels.weixin.qq.com/platform/statistic/post"
POST_LIST_URL = "https://channels.weixin.qq.com/platform/post/list"


def _probe_page(page, target_url: str) -> dict:
    captured: list[dict] = []

    def on_response(response) -> None:
        url = response.url
        if response.status != 200 or "mmfinderassistant-bin" not in url:
            return
        try:
            body = response.json()
        except Exception:
            return
        if not isinstance(body, dict):
            return
        item = {
            "api": url.split("mmfinderassistant-bin/")[-1].split("?")[0],
            "errCode": body.get("errCode"),
        }
        data = body.get("data") or {}
        if isinstance(data, dict):
            item["data_keys"] = list(data.keys())[:15]
            rows = data.get("list")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                item["list_len"] = len(rows)
                item["first_keys"] = sorted(rows[0].keys())
        captured.append(item)

    page.on("response", on_response)
    page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(12_000)
    page.remove_listener("response", on_response)
    return {"url": page.url, "apis": captured}


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

    temp_state = Config.ROOT_DIR / "data/publish/_probe_wechat_stat.json"
    temp_state.write_bytes(load_encrypted(Config.ROOT_DIR / account.session_path))
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_context(storage_state=str(temp_state)).new_page()

    results = {
        "statistic_post": _probe_page(page, STAT_URL),
        "post_list": _probe_page(page, POST_LIST_URL),
    }
    out = Config.ROOT_DIR / "data/publish/probe_wechat_stat_compare.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")
    for label, data in results.items():
        print(f"=== {label} ===")
        print("final_url:", data["url"])
        for item in data["apis"]:
            print(" ", item)

    browser.close()
    playwright.stop()
    temp_state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
