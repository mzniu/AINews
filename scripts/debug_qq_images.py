"""Debug Tencent article image extraction."""
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ingestion.adapters.qq_news import QqNewsAdapter
from src.utils.config import Config

ARTICLE_ID = "20260810A04WOP00"
url = f"https://view.inews.qq.com/a/{ARTICLE_ID}"
headers = {"User-Agent": Config.USER_AGENT, "Referer": "https://news.qq.com/ch/fx"}
html = requests.get(url, timeout=30, headers=headers).text
match = re.search(r"window\.DATA\s*=\s*(\{.*?\});\s*\n", html, re.S)
data = json.loads(match.group(1))
origin = (data.get("originContent") or {}).get("text", "")
print("origin html len", len(origin))
print("origin text len", len(BeautifulSoup(origin, "lxml").get_text(strip=True)))
print("origin img tags", len(BeautifulSoup(origin, "lxml").select("img")))

page_soup = BeautifulSoup(html, "lxml")
dom_imgs = page_soup.select("#article-content img, .content-article img")
print("dom img tags", len(dom_imgs))
for idx, img in enumerate(dom_imgs[:5]):
    attrs = {k: img.get(k) for k in ("src", "data-src", "data-original", "data-lazy-src") if img.get(k)}
    print(" dom", idx, attrs)

adapter = QqNewsAdapter("qq_news_fx", "https://news.qq.com")
detail = adapter.parse_detail_html(html, url=url)
print("adapter images", len(detail.images))
for img in detail.images:
    print(" ", img[:100])
