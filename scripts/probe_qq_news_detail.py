"""Probe Tencent article detail fetch."""
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config

headers = {
    "User-Agent": Config.USER_AGENT,
    "Referer": "https://news.qq.com/ch/fx",
}

def fetch_list(page=0):
    r = requests.post(
        "https://i.news.qq.com/web_feed/getPCList",
        json={
            "base_req": {"from": "pc"},
            "forward": "2",
            "channel_id": "news_news_fx",
            "page": page,
        },
        timeout=20,
        headers={**headers, "Content-Type": "application/json"},
    )
    r.raise_for_status()
    data = r.json()
    items = data.get("data") or []
    refs = []
    for block in items:
        subs = block.get("sub_item") or [block]
        for item in subs:
            aid = item.get("id")
            title = item.get("title")
            if not aid or not title:
                continue
            refs.append(item)
    return refs

refs = fetch_list(0)
print("refs", len(refs))
item = refs[0]
print(json.dumps(item, ensure_ascii=False, indent=2)[:2000])

article_id = item["id"]
# common tencent article url patterns
candidates = [
    f"https://news.qq.com/rain/a/{article_id}",
    f"https://new.qq.com/rain/a/{article_id}",
    f"https://news.qq.com/a/{article_id}",
    f"https://new.qq.com/a/{article_id}",
    f"https://view.inews.qq.com/a/{article_id}",
]
for url in candidates:
    try:
        r = requests.get(url, timeout=20, headers=headers, allow_redirects=True)
        print("GET", url, "->", r.url, r.status_code, len(r.text))
        if r.status_code == 200 and len(r.text) > 5000:
            soup = BeautifulSoup(r.text, "lxml")
            title = soup.select_one("h1")
            content = soup.select_one("#article-content, .content-article, .LEFT, .content")
            print(" title", title.get_text(strip=True)[:80] if title else None)
            if content:
                print(" content chars", len(content.get_text("\n", strip=True)))
            # window.DATA
            m = re.search(r"window\.DATA\s*=\s*(\{.*?\});", r.text, re.S)
            if m:
                print(" found window.DATA", len(m.group(1)))
            m2 = re.search(r"__NEXT_DATA__", r.text)
            print(" next", bool(m2))
            Path(ROOT / "tests/fixtures/qq_news").mkdir(parents=True, exist_ok=True)
            (ROOT / "tests/fixtures/qq_news/detail_sample.html").write_text(r.text, encoding="utf-8")
            break
    except Exception as exc:
        print(url, exc)

# detail API attempts
detail_apis = [
    ("https://i.news.qq.com/getQQNewsFullInfo", {"id": article_id}),
    ("https://i.news.qq.com/getQQNewsNormalContent", {"id": article_id}),
    ("https://r.inews.qq.com/getQQNewsFullInfo", {"id": article_id}),
    ("https://r.inews.qq.com/getQQNewsNormalContent", {"id": article_id}),
]
for api, params in detail_apis:
    r = requests.get(api, params=params, timeout=20, headers=headers)
    print("API", api, r.status_code, r.text[:300])
