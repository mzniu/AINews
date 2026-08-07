"""Phase 0 gate: WeChat Channels QR login + manual upload probe."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
LOGIN_URL = "https://channels.weixin.qq.com/login.html"
CREATOR_URL = "https://channels.weixin.qq.com/platform/post/create"
SESSION_OUT = ROOT / "data" / "publish" / "spike_storage_state.json"
SELECTORS_DOC = ROOT / "docs" / "publishing" / "wechat_channels_selectors.md"

# Fill after manual probe — see docs/publishing/wechat_channels_selectors.md
SELECTORS = {
    "file_input": 'input[type="file"]',
    "title_input": 'textarea[placeholder*="标题"], input[placeholder*="标题"]',
    "description_input": 'textarea[placeholder*="描述"], textarea[placeholder*="简介"]',
    "publish_button": 'button:has-text("发表"), button:has-text("发布")',
}


def login_and_save_state(*, headless: bool = False) -> Path:
    SESSION_OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("请在浏览器中扫码登录，登录成功后按 Enter…")
        input()
        context.storage_state(path=str(SESSION_OUT))
        browser.close()
    return SESSION_OUT


def upload_video(session_path: Path, video_path: Path, title: str) -> dict:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        page.goto(CREATOR_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.locator(SELECTORS["file_input"]).first.set_input_files(str(video_path.resolve()))
        page.wait_for_timeout(3000)
        title_loc = page.locator(SELECTORS["title_input"]).first
        title_loc.wait_for(state="visible", timeout=60_000)
        title_loc.fill(title)
        page.wait_for_timeout(1000)
        try:
            page.locator(SELECTORS["publish_button"]).first.click(timeout=10_000)
            page.wait_for_timeout(5000)
            success = True
            error = None
        except PlaywrightTimeoutError as exc:
            success = False
            error = str(exc)
        browser.close()
    return {"success": success, "title": title, "video": str(video_path), "error": error}


def main() -> int:
    parser = argparse.ArgumentParser(description="WeChat Channels publish spike")
    parser.add_argument("--video", type=Path, help="MP4 path under data/videos/")
    parser.add_argument("--title", default=f"AINews Spike {datetime.now():%Y%m%d_%H%M}")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--login-only", action="store_true")
    args = parser.parse_args()

    session = SESSION_OUT
    if not session.exists():
        session = login_and_save_state(headless=args.headless)
    elif args.login_only:
        session = login_and_save_state(headless=args.headless)

    if args.login_only:
        print(f"Session saved: {session}")
        return 0

    if args.video is None:
        print("--video is required unless --login-only", file=sys.stderr)
        return 1
    if not args.video.exists():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 1

    result = upload_video(session, args.video, args.title)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
