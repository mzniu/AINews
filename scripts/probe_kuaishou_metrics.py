"""Probe Kuaishou creator metrics APIs and DOM for debugging."""
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

MANAGE_URL = "https://cp.kuaishou.com/article/manage/video"
PROFILE_URL = "https://cp.kuaishou.com/profile"


def main() -> None:
    factory = get_session_factory()
    with factory() as session:
        account = (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == "kuaishou", PublisherAccount.status == "active")
            .first()
        )
    if account is None:
        print("No active kuaishou account")
        return

    session_path = Config.ROOT_DIR / account.session_path
    print(f"account={account.id} session={session_path}")

    temp_state = Config.ROOT_DIR / "data" / "publish" / "_probe_metrics_state.json"
    captured: list[dict] = []

    def on_response(response) -> None:
        url = response.url
        if response.status != 200:
            return
        if not any(
            key in url
            for key in ("photo", "video", "work", "content", "manage", "rest", "graphql", "list")
        ):
            return
        try:
            body = response.json()
        except Exception:
            return
        item = {
            "url": url,
            "method": response.request.method,
            "keys": list(body.keys()) if isinstance(body, dict) else type(body).__name__,
            "result": body.get("result") if isinstance(body, dict) else None,
        }
        captured.append(item)
        if "photo/list" in url or "photoList" in url:
            out = Config.ROOT_DIR / "data" / "publish" / "probe_kuaishou_photo_list.json"
            out.write_text(json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")

    temp_state.write_bytes(load_encrypted(session_path))
    playwright = sync_playwright().start()
    browser = launch_publish_browser(playwright, headless=False)
    context = create_publish_browser_context(browser, storage_state=str(temp_state))
    page = context.new_page()
    page.on("response", on_response)

    page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2000)
    print("profile url:", page.url)

    page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8000)
    print("manage url:", page.url)

    photo_urls = [item for item in captured if "photo" in item["url"] or "works/v2/video" in item["url"]]
    print("photo-related responses:", len(photo_urls))
    for item in photo_urls:
        print(" -", item)

    dom = page.evaluate(
        """() => {
      const cards = Array.from(document.querySelectorAll('[class*="item"], [class*="card"], [class*="video"], tr, li'))
        .slice(0, 15)
        .map(el => ({
          tag: el.tagName,
          cls: (el.className && el.className.toString) ? el.className.toString().slice(0, 80) : '',
          text: (el.innerText || '').slice(0, 180),
          attrs: Array.from(el.attributes || []).slice(0, 6).map(a => [a.name, String(a.value).slice(0, 80)]),
        }));
      const html = document.body.innerHTML;
      const photoIds = Array.from(html.matchAll(/photoId=([A-Za-z0-9_-]+)/g)).map(m => m[1]);
      const workIds = Array.from(html.matchAll(/workId=([A-Za-z0-9_-]+)/g)).map(m => m[1]);
      const dataIds = Array.from(document.querySelectorAll('[data-photo-id], [data-work-id], [data-id]'))
        .map(el => el.getAttribute('data-photo-id') || el.getAttribute('data-work-id') || el.getAttribute('data-id'));
      return { cards, photoIds: [...new Set(photoIds)].slice(0, 10), workIds: [...new Set(workIds)].slice(0, 10), dataIds: [...new Set(dataIds)].slice(0, 10) };
    }"""
    )
    print("dom detail:", json.dumps(dom, ensure_ascii=False, indent=2)[:5000])
    print("captured responses:", len(captured))
    for item in captured[:20]:
        print(" -", item["url"][:120], item["keys"])

    api_try = page.evaluate(
        """async () => {
      const candidates = [
        '/rest/cp/works/v2/video/pc/photo/list',
        '/rest/cp/works/v2/video/pc/photo/list?queryType=0&page=1&count=20',
        '/rest/cp/works/v2/video/pc/photo/list?queryType=1&page=1&count=20',
        '/rest/cp/works/v2/video/pc/photo/list?queryType=2&page=1&count=20',
      ];
      const results = [];
      for (const path of candidates) {
        try {
          const resp = await fetch(path, { credentials: 'include' });
          const text = await resp.text();
          results.push({ path, status: resp.status, sample: text.slice(0, 300) });
        } catch (e) {
          results.push({ path, error: String(e) });
        }
      }
      return results;
    }"""
    )
    print("api_try:", json.dumps(api_try, ensure_ascii=False, indent=2))

    browser.close()
    playwright.stop()
    temp_state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
