#!/usr/bin/env python3
"""Manual spike: Kuaishou creator QR login."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://cp.kuaishou.com/"


def main() -> None:
    parser = argparse.ArgumentParser(description="Kuaishou login spike")
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
        page.wait_for_timeout(2000)
        try:
            page.locator("text=扫码登录").first.click(timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        print(f"Opened {LOGIN_URL} — scan QR in browser…")

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            url = page.url.lower()
            if "login" not in url and "passport" not in url:
                print(f"Login success URL: {page.url}")
                page.goto("https://cp.kuaishou.com/article/publish/video", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                state_path = out_dir / "kuaishou_storage_state.json"
                state_path.write_text(
                    json.dumps(context.storage_state(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"Saved {state_path}")
                if args.login_only:
                    input("Press Enter to close…")
                browser.close()
                return
            if "passport" in url:
                try:
                    page.locator("text=扫码登录").first.click(timeout=3000)
                except Exception:
                    pass
            time.sleep(2)

        print("Timeout")
        browser.close()


if __name__ == "__main__":
    main()
