"""Manual spike: Douyin creator video upload probe."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.adapters.douyin_form import (
    fill_douyin_description,
    fill_douyin_title,
    upload_douyin_video,
    wait_for_douyin_editor,
)

LOGIN_URL = "https://creator.douyin.com/"
CREATOR_URL = "https://creator.douyin.com/creator-micro/content/upload"
SESSION_OUT = ROOT / "data" / "publish" / "spike" / "douyin_storage_state.json"


def login_and_save_state() -> Path:
    SESSION_OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("请在浏览器中扫码登录，登录成功后按 Enter…")
        input()
        context.storage_state(path=str(SESSION_OUT))
        browser.close()
    return SESSION_OUT


def upload_probe(session_path: Path, video_path: Path, title: str, description: str) -> dict:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        page.goto(CREATOR_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        ok = upload_douyin_video(page, str(video_path.resolve()), timeout_ms=120_000)
        if not ok:
            browser.close()
            return {"success": False, "error": "upload surface not found"}
        wait_for_douyin_editor(page, timeout_ms=120_000)
        fill_douyin_title(page, title, timeout_ms=60_000)
        if description:
            fill_douyin_description(page, description, timeout_ms=60_000)
        print("素材已上传并填好文案，请手动点击发布，完成后按 Enter…")
        input()
        browser.close()
    return {"success": True, "title": title, "video": str(video_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Douyin publish spike")
    parser.add_argument("--video", type=Path, help="MP4 path under data/videos/")
    parser.add_argument("--title", default=f"AINews Spike {datetime.now():%Y%m%d_%H%M}")
    parser.add_argument("--description", default="AINews 抖音发布 Spike 测试")
    parser.add_argument("--login-only", action="store_true")
    args = parser.parse_args()

    session = SESSION_OUT
    if not session.exists() or args.login_only:
        session = login_and_save_state()
        if args.login_only:
            print(f"Saved session to {session}")
            return 0

    if not args.video:
        print("Provide --video for upload probe")
        return 1
    result = upload_probe(session, args.video, args.title, args.description)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
