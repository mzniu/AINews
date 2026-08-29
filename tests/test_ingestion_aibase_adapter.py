"""AIbase news adapter fixture tests."""
from pathlib import Path

from services.ingestion.adapters.aibase_news import AibaseNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "aibase"


def test_parse_detail_aibase_news_fixture():
    html = (FIXTURE_DIR / "detail_news.html").read_text(encoding="utf-8")
    adapter = AibaseNewsAdapter(source_id="aibase_daily", base_url="https://www.aibase.com")
    detail = adapter.parse_detail_html(html, url="https://www.aibase.com/zh/news/30535")
    assert "AI" in detail.title or "RayNeo" in detail.title or len(detail.title) >= 8
    assert len(detail.content_text) > 200


def test_parse_detail_aibase_daily_fixture():
    html = (FIXTURE_DIR / "detail_daily.html").read_text(encoding="utf-8")
    adapter = AibaseNewsAdapter(source_id="aibase_daily", base_url="https://www.aibase.com")
    detail = adapter.parse_detail_html(html, url="https://www.aibase.com/zh/daily/30532")
    assert len(detail.title) >= 8
    assert len(detail.content_text) > 500
