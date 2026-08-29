"""Inspect originContent structure for images."""
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

url = "https://view.inews.qq.com/a/20260810A04WOP00"
html = requests.get(url, timeout=30, headers={"User-Agent": Config.USER_AGENT, "Referer": "https://news.qq.com/ch/fx"}).text
data = json.loads(re.search(r"window\.DATA\s*=\s*(\{.*?\});\s*\n", html, re.S).group(1))
origin = (data.get("originContent") or {}).get("text", "")
Path(ROOT / "tests/fixtures/qq_news/detail_multi_img_origin.html").write_text(origin, encoding="utf-8")

gtimg_urls = re.findall(r"https://inews\.gtimg\.com/[^\s\"'<>]+", origin)
print("gtimg urls in origin string", len(gtimg_urls))
print("sample", gtimg_urls[:5])

soup = BeautifulSoup(origin, "lxml")
print("tags sample", [t.name for t in soup.find_all(True)[:20]])
# qq uses data-src in divs?
for sel in ["img", "qqmusic", "mpvoice", "section", "[data-src]", "[style*='background']"]:
    els = soup.select(sel)
    print(sel, len(els))
    if els and sel in ("[data-src]", "section"):
        for el in els[:3]:
            print(" ", el.name, el.get("data-src"), (el.get("style") or "")[:80])

# check attribute_img_list or similar in full DATA
for key in data:
    if "img" in key.lower() or "photo" in key.lower() or "pic" in key.lower():
        print("data key", key, str(data[key])[:200])
