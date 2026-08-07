"""Probe and save 36kr fixtures."""
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

headers = {"User-Agent": Config.USER_AGENT}
list_url = "https://www.36kr.com/information/AI/"
response = requests.get(list_url, timeout=20, headers=headers)
response.encoding = "utf-8"
soup = BeautifulSoup(response.text, "lxml")

pattern = re.compile(r"/p/\d+")
picked = None
for link in soup.find_all("a", href=pattern):
    href = link.get("href", "")
    title = (link.get_text(strip=True) or "").strip()
    if len(title) < 8:
        continue
    if href.startswith("/"):
        href = "https://www.36kr.com" + href
    picked = (title, href)
    break

if not picked:
    raise SystemExit("No article link found")

title, detail_url = picked
print("pick:", title[:60], detail_url)
detail_resp = requests.get(detail_url, timeout=20, headers=headers)
detail_resp.encoding = "utf-8"
detail_soup = BeautifulSoup(detail_resp.text, "lxml")
content = detail_soup.select_one("div.article-content")
print("detail chars:", len(content.get_text("\n", strip=True)) if content else 0)
print("images:", len(content.select("img")) if content else 0)

fixture_dir = ROOT / "tests" / "fixtures" / "kr36"
fixture_dir.mkdir(parents=True, exist_ok=True)
(fixture_dir / "list_ai.html").write_text(response.text, encoding="utf-8")
(fixture_dir / "detail_sample.html").write_text(detail_resp.text, encoding="utf-8")
print("fixtures saved to", fixture_dir)
