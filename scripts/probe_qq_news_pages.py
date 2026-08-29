"""Test Tencent list pagination variants."""
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
    "Content-Type": "application/json",
}


def ids_from_payload(payload):
    r = requests.post(
        "https://i.news.qq.com/web_feed/getPCList",
        json=payload,
        timeout=20,
        headers=headers,
    )
    data = r.json()
    if data.get("code") != 0:
        return data.get("code"), []
    out = []
    for block in data.get("data") or []:
        for item in block.get("sub_item") or [block]:
            aid = item.get("id")
            if aid and item.get("title"):
                out.append(aid)
    return data.get("code"), out


base = {
    "base_req": {"from": "pc"},
    "forward": "2",
    "channel_id": "news_news_fx",
}

for page in [0, 1, 2, 3]:
    code, ids = ids_from_payload({**base, "page": page})
    print("page", page, "code", code, "first", ids[:2], "last", ids[-2:])

for forward in ["0", "1", "2", "22", "23"]:
    code, ids = ids_from_payload({**base, "forward": forward, "page": 0})
    print("forward", forward, "n", len(ids), "first", ids[:1])

# cursor style using last id
_, ids0 = ids_from_payload({**base, "page": 0})
last = ids0[-1]
for payload in [
    {**base, "page": 1, "pull_down": 1},
    {**base, "page": 1, "refresh_type": 1},
    {**base, "page": 0, "forward": "1", "ids": last},
    {**base, "page": 0, "forward": "1", "last_id": last},
    {**base, "page": 0, "forward": "1", "offset_info": last},
]:
    code, ids = ids_from_payload(payload)
    print("cursor try", payload.get("forward"), payload.get("page"), list(payload.keys())[-1:], "n", len(ids), "same", ids[:2] == ids0[:2])
