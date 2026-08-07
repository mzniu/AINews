#!/usr/bin/env python3
"""Manual spike: Douyin creator QR login. Run with --login-only."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://creator.douyin.com/"


def main() -> None:
    parser = argparse.ArgumentParser(description="Douyin login spike")
    parser.add_argument("--login-only", action="store_true", help="Open browser and wait for manual QR scan")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for login")
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parents[1] / "data" / "publish" / "spike"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print(f"Opened {LOGIN_URL}")
        print("Please scan QR in the browser window…")

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            url = page.url
            if "login" not in url.lower() and "passport" not in url.lower():
                print(f"Login success URL: {url}")
                state = context.storage_state()
                state_path = out_dir / "douyin_storage_state.json"
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Saved storage state to {state_path}")
                if args.login_only:
                    input("Press Enter to close browser…")
                browser.close()
                return
            time.sleep(2)

        print("Timeout — login not detected. Update docs/publishing/douyin_selectors.md")
        browser.close()


if __name__ == "__main__":
    main()
