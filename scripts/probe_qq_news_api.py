"""Probe Tencent News finance channel API."""
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

headers = {
    "User-Agent": Config.USER_AGENT,
    "Referer": "https://news.qq.com/ch/fx",
}
base = "https://i.news.qq.com/web_feed/getPCList"

params_list = [
    {"channel_id": "news_news_fx", "page": 0, "is_pc": 1},
    {"channel_id": "news_news_fx", "offset": 0, "page": 0},
    {"chlid": "news_news_fx", "page": 0},
    {"channel_id": "news_news_finance", "page": 0, "is_pc": 1},
    {"channel_id": "news_news_fx", "page": 0, "is_pc": 1, "forward": "2"},
    {"channel_id": "news_news_fx", "page": 0, "is_pc": 1, "forward": "1"},
    {"channel_id": "news_news_fx", "page": 0, "is_pc": 1, "forward": "0"},
    {"channel_id": "news_news_fx", "page": 0, "is_pc": 1, "forward": "22"},
]

for params in params_list:
    r = requests.get(base, params=params, timeout=20, headers=headers)
    data = r.json()
    code = data.get("code")
    items = (data.get("data") or []) if isinstance(data.get("data"), list) else None
    print("params", params, "code", code, "items", len(items) if items else data.get("message"))
    if items:
        first = items[0]
        print(" first keys", list(first.keys())[:15])
        print(" title", first.get("title") or first.get("article_title"))
        print(" url", first.get("url") or first.get("link") or first.get("vurl"))
        break

# try POST
payloads = [
    {"channel_id": "news_news_fx", "page": 0, "is_pc": 1},
    {"base_req": {"from": "pc"}, "forward": "2", "channel_id": "news_news_fx", "page": 0},
]
for payload in payloads:
    r = requests.post(base, json=payload, timeout=20, headers={**headers, "Content-Type": "application/json"})
    try:
        data = r.json()
    except Exception:
        print("POST fail", r.status_code, r.text[:200])
        continue
    items = data.get("data") if isinstance(data.get("data"), list) else None
    print("POST", payload.keys(), "code", data.get("code"), "n", len(items) if items else data.get("message"))
    if items:
        print(json.dumps(items[0], ensure_ascii=False)[:500])
        break
