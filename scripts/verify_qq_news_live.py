"""Verify Tencent News finance channel live ingestion."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ingestion.adapters.qq_news import QqNewsAdapter


def main() -> None:
    adapter = QqNewsAdapter(
        source_id="qq_news_fx",
        base_url="https://news.qq.com",
        channel_id="news_news_fx",
        list_referer="https://news.qq.com/ch/fx",
    )
    items = adapter.discover_list("https://news.qq.com/ch/fx?page=0")
    print("list items:", len(items))
    if not items:
        raise SystemExit("no articles")
    first = items[0]
    print("first:", first.title[:80], first.url)
    detail = adapter.fetch_detail(first)
    print("content chars:", len(detail.content_text))
    print("images:", len(detail.images))
    if len(detail.content_text) < 100:
        raise SystemExit("article content too short")


if __name__ == "__main__":
    main()
