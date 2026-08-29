"""Find image arrays in window.DATA."""
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

url = "https://view.inews.qq.com/a/20260810A04WOP00"
html = requests.get(url, timeout=30, headers={"User-Agent": Config.USER_AGENT, "Referer": "https://news.qq.com/ch/fx"}).text
data = json.loads(re.search(r"window\.DATA\s*=\s*(\{.*?\});\s*\n", html, re.S).group(1))

found = []


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, str) and "gtimg.com" in v and any(ext in v for ext in (".jpg", "/0", "/641", "/1000")):
                found.append((p, v[:120]))
            if isinstance(v, list) and v and isinstance(v[0], str) and "gtimg" in v[0]:
                found.append((p, f"list[{len(v)}] {v[0][:80]}"))
            if len(path.split(".")) < 6:
                walk(v, p)
    elif isinstance(obj, list) and obj and len(path.split(".")) < 6:
        walk(obj[0], f"{path}[0]")


walk(data)
for item in found[:30]:
    print(item)
