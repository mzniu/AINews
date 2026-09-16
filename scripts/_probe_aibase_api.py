from __future__ import annotations

import json
from pathlib import Path

import requests

from src.utils.config import Config

ROOT = Path(__file__).resolve().parents[1]
headers = {"User-Agent": Config.USER_AGENT, "Accept": "application/json"}
candidates = [
    "https://www.aibase.com/api/news/list?page=1&pageSize=10",
    "https://www.aibase.com/api/v1/news/list?page=1",
    "https://api.aibase.com/news/list?page=1",
    "https://www.aibase.com/zh/api/news/list?page=1",
]
for url in candidates:
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print(url, r.status_code, r.text[:300])
        if r.ok and "news" in r.text.lower():
            Path("tests/fixtures/aibase/api_list.json").write_text(r.text, encoding="utf-8")
    except Exception as exc:
        print(url, exc)
