"""Probe view count fields across ingestion sources."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ingestion.view_count import parse_view_count
from src.utils.config import Config

HEADERS = {"User-Agent": Config.USER_AGENT}

URLS = {
    "aitnt": "http://travel.aitntnews.com/newDetail.html?newId=27818",
    "kr36": "https://www.36kr.com/p/3919391204415360",
    "qbitai": "https://www.qbitai.com/2026/07/464169.html",
    "leiphone": "https://www.leiphone.com/category/ai/mER69AfKN23gn4Yt.html",
}


def extract_initial_state(html: str) -> dict | None:
    match = re.search(r"window\.initialState\s*=\s*(\{.*?\})\s*;?\s*</script>", html, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for name, url in URLS.items():
        print(f"\n=== {name} ===")
        response = requests.get(url, timeout=20, headers=HEADERS)
        response.encoding = response.apparent_encoding or "utf-8"
        html = response.text
        parsed = parse_view_count(html)
        print("parsed view_count:", parsed)
        state = extract_initial_state(html)
        if state and name == "kr36":
            ad = state.get("articleDetail", {})
            print("kr36 likeCount:", ad.get("likeCount"))
            print("kr36 favoriteCount:", ad.get("favoriteCount"))


if __name__ == "__main__":
    main()
