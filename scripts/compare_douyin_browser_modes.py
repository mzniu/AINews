"""Compare headed vs headless Douyin session and work_list API."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.human_interaction import create_publish_browser_context, launch_publish_browser
from services.publishing.session_store import load_encrypted
from src.utils.config import Config

SESSION = Config.ROOT_DIR / "data/publish/sessions/b244d1ec3bb942d38eef749db75ca118.enc"
MANAGE = "https://creator.douyin.com/creator-micro/content/manage"
FETCH_JS = """
async () => {
  const params = new URLSearchParams({
    status: '0', count: '20', max_cursor: '0',
    scene: 'star_atlas', device_platform: 'android', aid: '1128'
  });
  const resp = await fetch(`https://creator.douyin.com/janus/douyin/creator/pc/work_list?${params}`, {credentials:'include'});
  return await resp.json();
}
"""


def probe(headless: bool, use_stealth: bool) -> dict:
    temp = Config.ROOT_DIR / "data/publish/_probe.json"
    temp.write_bytes(load_encrypted(SESSION))
    pw = sync_playwright().start()
    if use_stealth:
        browser = launch_publish_browser(pw, headless=headless)
        context = create_publish_browser_context(browser, storage_state=str(temp))
    else:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(temp))
    page = context.new_page()
    page.goto(MANAGE, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)
    text = page.evaluate("() => document.body.innerText || ''")
    payload = page.evaluate(FETCH_JS)
    result = {
        "headless": headless,
        "stealth": use_stealth,
        "url": page.url,
        "login_url_check": is_login_success_url(page.url, ["login", "passport"]),
        "has_qr_login": "扫码登录" in text,
        "status_code": payload.get("status_code") if isinstance(payload, dict) else None,
        "item_count": len(payload.get("items") or payload.get("aweme_list") or []),
    }
    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)
    return result


def main() -> None:
    cases = [
        probe(False, False),
        probe(True, False),
        probe(False, True),
        probe(True, True),
    ]
    print(json.dumps(cases, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
