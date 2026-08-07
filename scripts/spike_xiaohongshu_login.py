#!/usr/bin/env python3
"""Manual spike: Xiaohongshu creator QR login."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://creator.xiaohongshu.com/login"


def main() -> None:
    parser = argparse.ArgumentParser(description="Xiaohongshu login spike")
    parser.add_argument("--login-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parents[1] / "data" / "publish" / "spike"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        try:
            page.locator(".login-box-container img").first.click(timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        print(f"Opened {LOGIN_URL} — scan QR in browser…")

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            url = page.url.lower()
            if "login" not in url and "passport" not in url:
                print(f"Login success URL: {page.url}")
                state_path = out_dir / "xiaohongshu_storage_state.json"
                state_path.write_text(
                    json.dumps(context.storage_state(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"Saved {state_path}")
                if args.login_only:
                    input("Press Enter to close…")
                browser.close()
                return
            time.sleep(2)

        print("Timeout")
        browser.close()


if __name__ == "__main__":
    main()
