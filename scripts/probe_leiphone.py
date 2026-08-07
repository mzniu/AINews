"""Fetch leiphone AI fixtures for adapter development."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

LIST_URL = "https://www.leiphone.com/category/ai"
HEADERS = {"User-Agent": Config.USER_AGENT}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    response = requests.get(LIST_URL, timeout=20, headers=HEADERS)
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "lxml")

    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not re.search(r"/category/ai/[A-Za-z0-9]+\.html", href):
            continue
        if href.startswith("/"):
            full = "https://www.leiphone.com" + href
        elif href.startswith("http"):
            full = href
        else:
            continue
        title = (anchor.get_text(strip=True) or "").strip()
        if full in seen or len(title) < 6:
            continue
        seen.add(full)
        links.append((title, full.split("?")[0]))

    print("links", len(links))
    if not links:
        return 1
    detail_url = links[0][1]
    print("sample", links[0][0][:50], detail_url)
    detail_resp = requests.get(detail_url, timeout=20, headers=HEADERS)
    detail_resp.encoding = detail_resp.apparent_encoding or "utf-8"
    detail_soup = BeautifulSoup(detail_resp.text, "lxml")
    for sel in [".lph-article-comView", ".article-content", "article", ".content"]:
        el = detail_soup.select_one(sel)
        if el:
            print(sel, len(el.get_text(strip=True)), len(el.select("img")))
    fixture_dir = ROOT / "tests" / "fixtures" / "leiphone"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "list_ai.html").write_text(response.text, encoding="utf-8")
    (fixture_dir / "detail_sample.html").write_text(detail_resp.text, encoding="utf-8")
    print("saved", fixture_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
