from __future__ import annotations

from pathlib import Path

from services.ingestion.http_client import get_text
from src.utils.config import Config

ROOT = Path(__file__).resolve().parents[1]
headers = {"User-Agent": Config.USER_AGENT}
urls = [
    ("aibase", "https://www.aibase.com/zh/news/30535", "detail_news.html"),
    ("aibase", "https://www.aibase.com/zh/daily/30532", "detail_daily.html"),
    ("sina", "https://k.sina.cn/article_1496814565_m593793e5033024crg.html", "detail_k_sina.html"),
]
for site, url, name in urls:
    html = get_text(url, headers=headers)
    out = ROOT / "tests/fixtures" / site / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(site, name, len(html))
