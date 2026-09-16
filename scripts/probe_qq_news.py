"""Probe Tencent News channel list and article APIs."""
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

headers = {"User-Agent": Config.USER_AGENT}
list_url = "https://news.qq.com/ch/fx"
response = requests.get(list_url, timeout=20, headers=headers)
response.encoding = "utf-8"
text = response.text
print("list status", response.status_code, "len", len(text))

for pat in ["channelId", "chlid", "tab_id", "inews.qq.com", "__NEXT_DATA__", "window.__"]:
    if pat in text:
        print("found marker:", pat)

api_candidates = sorted(set(re.findall(r"https?://[a-zA-Z0-9./_?=&%-]+", text)))
for url in api_candidates:
    if any(x in url for x in ("api", "feed", "get", "inews", "news.qq")):
        if "gtimg.com" not in url and "qqcdn" not in url:
            print("url:", url[:150])

# try known tencent news APIs
tests = [
    "https://i.news.qq.com/web_feed/getPCList",
    "https://i.news.qq.com/web_feed/getTagList",
    "https://r.inews.qq.com/gw/event/pc_hot_rank_list",
]
for api in tests:
    try:
        r = requests.get(api, timeout=15, headers=headers, params={"chlid": "finance"})
        print(api, r.status_code, r.text[:200])
    except Exception as exc:
        print(api, "ERR", exc)

# search inline json blobs
for m in re.finditer(r'"chlid"\s*:\s*"([^"]+)"', text):
    print("chlid", m.group(1))
for m in re.finditer(r'"channel_id"\s*:\s*"?([^",}]+)"?', text):
    print("channel_id", m.group(1))
