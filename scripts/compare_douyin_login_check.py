"""Compare Douyin login validation vs metrics page."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.session_store import load_encrypted
from src.utils.config import Config

SESSION = Config.ROOT_DIR / "data/publish/sessions/b244d1ec3bb942d38eef749db75ca118.enc"
EXCLUDES = ["login", "passport"]
URLS = [
    "https://creator.douyin.com/creator-micro/content/upload",
    "https://creator.douyin.com/creator-micro/content/manage",
    "https://creator.douyin.com/creator-micro/home",
]


def main() -> None:
    temp = Config.ROOT_DIR / "data/publish/_probe.json"
    temp.write_bytes(load_encrypted(SESSION))
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state=str(temp))
    page = ctx.new_page()
    for url in URLS:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2500)
        text = page.evaluate("() => document.body.innerText || ''")
        ok = is_login_success_url(page.url, EXCLUDES)
        print(f"URL: {url}")
        print(f"  final: {page.url}")
        print(f"  is_login_success_url: {ok}")
        print(f"  has_qr_login: {'扫码登录' in text}")
        print(f"  has_upload_ui: {'上传视频' in text or '高清发布' in text}")
        print()
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
