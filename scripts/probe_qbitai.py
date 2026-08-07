"""Probe qbitai.com list/detail structure for ingestion."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

HEADERS = {"User-Agent": Config.USER_AGENT}

CANDIDATE_LIST_URLS = [
    "https://www.qbitai.com/",
    "https://www.qbitai.com/latest",
    "https://www.qbitai.com/tag/ai",
    "https://www.qbitai.com/tag/人工智能",
]


def fetch(url: str) -> tuple[int, str]:
    response = requests.get(url, timeout=20, headers=HEADERS)
    response.encoding = response.apparent_encoding or "utf-8"
    return response.status_code, response.text


def extract_article_links(html: str, base: str = "https://www.qbitai.com") -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    patterns = [
        re.compile(r"/\d{4}/\d{2}/\d+\.html"),
        re.compile(r"https?://www\.qbitai\.com/\d{4}/\d{2}/\d+\.html"),
        re.compile(r"/article/\d+"),
        re.compile(r"https?://www\.qbitai\.com/article/\d+"),
    ]

    for link in soup.select("a[href]"):
        href = (link.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.startswith("/"):
            full = base.rstrip("/") + href
        elif href.startswith("http"):
            full = href
        else:
            continue
        if "qbitai.com" not in full:
            continue
        if not any(p.search(full) for p in patterns):
            continue
        title = (link.get_text(strip=True) or "").strip()
        if full in seen:
            continue
        seen.add(full)
        if len(title) >= 4:
            results.append((title, full.split("?")[0]))

    return results


def debug_links(html: str) -> None:
    soup = BeautifulSoup(html, "lxml")
    print("  sample anchors:")
    count = 0
    for link in soup.select("a[href]"):
        href = (link.get("href") or "").strip()
        title = (link.get_text(strip=True) or "").strip()
        if not href or len(title) < 4:
            continue
        if any(x in href for x in ["/20", "article", "archives", "tag"]):
            print(f"    {title[:40]} -> {href[:80]}")
            count += 1
            if count >= 8:
                break


def probe_detail(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        "div.article-content",
        "div.content",
        "article",
        ".article",
        ".entry-content",
        ".article-detail",
        ".article_content",
        "#article-content",
    ]
    content_len = 0
    hit = None
    for sel in selectors:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > content_len:
            content_len = len(el.get_text(strip=True))
            hit = sel
    title = None
    for sel in ["h1", "h1.article-title", ".article-title"]:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            break
    imgs = 0
    if hit:
        imgs = len(soup.select_one(hit).select("img"))
    return {
        "title": title,
        "content_selector": hit,
        "content_chars": content_len,
        "images": imgs,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Qbitai probe ===\n")

    best_list = None
    best_links: list[tuple[str, str]] = []
    for list_url in CANDIDATE_LIST_URLS:
        try:
            status, html = fetch(list_url)
        except Exception as exc:
            print(f"[{list_url}] FAIL {exc}")
            continue
        links = extract_article_links(html)
        print(f"[{list_url}] HTTP {status} links={len(links)}")
        if not links:
            debug_links(html)
        if len(links) > len(best_links):
            best_links = links
            best_list = list_url
        for title, url in links[:3]:
            print(f"  - {title[:50]} -> {url}")

    if not best_links:
        print("\nFAIL: no article links found on any list page")
        return 1

    print(f"\nBest list: {best_list} ({len(best_links)} links)")
    detail_url = best_links[0][1]
    print(f"\nProbing detail: {detail_url}")
    status, detail_html = fetch(detail_url)
    info = probe_detail(detail_url, detail_html)
    print(f"HTTP {status}")
    for key, value in info.items():
        print(f"  {key}: {value}")

    if info["content_chars"] < 200:
        print("\nFAIL: detail content too short")
        return 1

    fixture_dir = ROOT / "tests" / "fixtures" / "qbitai"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    _, list_html = fetch(best_list)
    (fixture_dir / "list_home.html").write_text(list_html, encoding="utf-8")
    (fixture_dir / "detail_sample.html").write_text(detail_html, encoding="utf-8")
    print(f"\nFixtures saved: {fixture_dir}")
    print("\nPASS: qbitai is crawlable with static HTML")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
