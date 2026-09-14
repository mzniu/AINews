"""Probe statistic/post -> 单篇视频 tab and per-video detail APIs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.human_pacing import human_pause
from services.publishing.human_interaction import open_stealth_browser
from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

STAT_URL = "https://channels.weixin.qq.com/platform/statistic/post"

CLICK_SINGLE_TAB_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    for (const el of root.querySelectorAll('button, [role="tab"], .tab, span, div, a, li')) {
      const text = (el.innerText || '').trim();
      if (text === '单篇视频' || text.startsWith('单篇视频')) {
        el.click();
        return { clicked: true, text, cls: String(el.className || '').slice(0, 80) };
      }
    }
  }
  const snippets = [];
  for (const root of roots) {
    root.querySelectorAll('button, [role="tab"], .tab, span, div, a, li').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (/视频|单篇|全部/.test(text) && text.length < 20) {
        snippets.push({ text, cls: String(el.className || '').slice(0, 60) });
      }
    });
  }
  return { clicked: false, candidates: snippets.slice(0, 30) };
}
"""

CLICK_FIRST_VIDEO_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  for (const root of roots) {
    const items = root.querySelectorAll(
      'tr, [class*="post"], [class*="video"], [class*="feed"], [class*="item"], [class*="row"]'
    );
    for (const el of items) {
      const text = (el.innerText || '').trim();
      if (text.length < 30) continue;
      if (/播放|点赞|评论|完播|转发|收藏/.test(text) && !/全部视频|单篇视频|关键指标/.test(text)) {
        el.click();
        return { clicked: true, text: text.slice(0, 160), cls: String(el.className || '').slice(0, 80) };
      }
    }
  }
  return { clicked: false };
}
"""

SCAN_PAGE_JS = """
() => {
  const roots = [document];
  const wujie = document.querySelector('wujie-app');
  if (wujie && wujie.shadowRoot) roots.push(wujie.shadowRoot);
  const tabs = [];
  const rows = [];
  for (const root of roots) {
    root.querySelectorAll('button, [role="tab"], .tab, span, div, a, li').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (/视频|单篇|全部|关键/.test(text) && text.length < 24) {
        tabs.push({ text, cls: String(el.className || '').slice(0, 60) });
      }
    });
    root.querySelectorAll('tr, [class*="post"], [class*="video"], [class*="feed"], [class*="item"]').forEach((el) => {
      const text = (el.innerText || '').trim();
      if (text.length > 20 && text.length < 300) rows.push({ text: text.slice(0, 160), cls: String(el.className || '').slice(0, 60) });
    });
  }
  return {
    url: location.href,
    title: document.title,
    body: (document.body.innerText || '').slice(0, 1200),
    tabs: tabs.slice(0, 20),
    rows: rows.slice(0, 12),
  };
}
"""


def _summarize_body(body: dict) -> dict:
    data = body.get("data")
    out: dict = {"errCode": body.get("errCode"), "errMsg": body.get("errMsg")}
    if isinstance(data, dict):
        out["data_keys"] = list(data.keys())[:30]
        items = data.get("list")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            out["list_len"] = len(items)
            out["first_keys"] = sorted(items[0].keys())
            sample = {k: items[0].get(k) for k in sorted(items[0].keys()) if k not in ("desc", "commentList")}
            out["first_sample"] = sample
    elif isinstance(data, list):
        out["list_len"] = len(data)
        if data and isinstance(data[0], dict):
            out["first_keys"] = sorted(data[0].keys())
    return out


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

    temp = Config.ROOT_DIR / "data/publish/_probe_single_video.json"
    temp.write_bytes(load_encrypted(Config.ROOT_DIR / account.session_path))

    captured: dict[str, dict] = {}
    pw = sync_playwright().start()
    browser, ctx = open_stealth_browser(pw, headless=False, storage_state=str(temp))
    page = ctx.new_page()

    def on_response(response) -> None:
        url = response.url
        if "mmfinderassistant-bin" not in url or response.status not in (200, 201):
            return
        api = url.split("mmfinderassistant-bin/")[-1].split("?")[0]
        try:
            body = response.json()
        except Exception:
            return
        if not isinstance(body, dict):
            return
        captured[api] = _summarize_body(body)

    page.on("response", on_response)
    page.goto(STAT_URL, wait_until="domcontentloaded", timeout=60_000)
    human_pause(page, "page_load")
    page.wait_for_timeout(5000)
    before_tab = page.evaluate(SCAN_PAGE_JS)

    tab_click = page.evaluate(CLICK_SINGLE_TAB_JS)
    page.wait_for_timeout(8000)
    after_tab = page.evaluate(SCAN_PAGE_JS)

    video_click = page.evaluate(CLICK_FIRST_VIDEO_JS)
    page.wait_for_timeout(8000)
    after_video = page.evaluate(SCAN_PAGE_JS)

    result = {
        "tab_click": tab_click,
        "video_click": video_click,
        "dom": {"before_tab": before_tab, "after_tab": after_tab, "after_video": after_video},
        "apis": captured,
    }
    out = Config.ROOT_DIR / "data/publish/probe_wechat_single_video_tab.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")
    print("tab_click", tab_click)
    print("video_click", video_click)
    for api, summary in sorted(captured.items()):
        if "statistic" in api or "post" in api:
            print(api, summary)

    browser.close()
    pw.stop()
    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
