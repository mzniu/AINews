#!/usr/bin/env python3
"""Manual spike: Kuaishou creator QR login + video publish probe."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.adapters.kuaishou_form import (
    advance_past_kuaishou_upload_window,
    compose_kuaishou_description,
    dismiss_kuaishou_guide_tooltips,
    fill_kuaishou_description,
    fill_kuaishou_title,
    upload_kuaishou_video,
    wait_for_kuaishou_editor,
    wait_for_kuaishou_video_ready,
)

LOGIN_URL = "https://cp.kuaishou.com/"
CREATOR_URL = "https://cp.kuaishou.com/article/publish/video"
PROFILE_URL = "https://cp.kuaishou.com/profile"
QR_SWITCH_SELECTOR = "text=扫码登录"
SESSION_OUT = ROOT / "data" / "publish" / "spike" / "kuaishou_storage_state.json"


def _switch_to_qr(page) -> None:
    try:
        page.locator(QR_SWITCH_SELECTOR).first.click(timeout=5000)
        page.wait_for_timeout(1000)
    except Exception:
        pass


def login_and_save_state(timeout: int) -> Path:
    SESSION_OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        _switch_to_qr(page)
        print(f"Opened {LOGIN_URL} — scan QR in browser…")

        deadline = time.time() + timeout
        while time.time() < deadline:
            url = page.url.lower()
            if "login" not in url and "passport" not in url:
                page.goto(PROFILE_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                context.storage_state(path=str(SESSION_OUT))
                browser.close()
                return SESSION_OUT
            if "passport" in url:
                _switch_to_qr(page)
            time.sleep(2)

        browser.close()
        raise SystemExit("Login timeout")


def upload_probe(session_path: Path, video_path: Path, title: str, description: str, tags: list[str]) -> dict:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        page.goto(CREATOR_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        ok = upload_kuaishou_video(page, str(video_path.resolve()), timeout_ms=120_000)
        if not ok:
            browser.close()
            return {"success": False, "error": "upload surface not found"}
        wait_for_kuaishou_video_ready(page, timeout_ms=180_000)
        advance_past_kuaishou_upload_window(page, timeout_ms=120_000)
        dismiss_kuaishou_guide_tooltips(page)
        wait_for_kuaishou_editor(page, timeout_ms=120_000)
        fill_kuaishou_title(page, title, timeout_ms=60_000)
        body = compose_kuaishou_description(description, tags)
        if body:
            fill_kuaishou_description(page, body, timeout_ms=60_000)
        print("素材已上传并填好文案，请手动点击发布，完成后按 Enter…")
        input()
        browser.close()
    return {"success": True, "title": title, "video": str(video_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Kuaishou login/publish spike")
    parser.add_argument("--video", type=Path, help="MP4 path under data/videos/")
    parser.add_argument("--title", default=f"AINews Spike {datetime.now():%Y%m%d_%H%M}")
    parser.add_argument("--description", default="AINews 快手发布 Spike 测试")
    parser.add_argument("--tags", default="AI,科技")
    parser.add_argument("--login-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    session = SESSION_OUT
    if not session.exists() or args.login_only:
        session = login_and_save_state(args.timeout)
        print(f"Saved session to {session}")
        if args.login_only:
            return 0

    if not args.video:
        print("Provide --video for upload probe")
        return 1
    tags = [item.strip() for item in args.tags.split(",") if item.strip()]
    result = upload_probe(session, args.video, args.title, args.description, tags)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
