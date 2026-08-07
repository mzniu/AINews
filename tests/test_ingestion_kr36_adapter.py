"""36kr adapter parsing from HTML fixtures."""
from pathlib import Path

from services.ingestion.adapters.kr36_news import Kr36NewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "kr36"


def test_parse_list_page_from_fixture():
    html = (FIXTURE_DIR / "list_ai.html").read_text(encoding="utf-8")
    adapter = Kr36NewsAdapter(
        source_id="kr36_ai",
        base_url="https://www.36kr.com",
    )
    items = adapter.parse_list_html(html)
    assert len(items) >= 10
    first = items[0]
    assert "/p/" in first.url
    assert "世界模型" in first.title or len(first.title) >= 8
    assert first.theme == "AI"
    assert first.summary


def test_parse_detail_page_from_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    adapter = Kr36NewsAdapter(
        source_id="kr36_ai",
        base_url="https://www.36kr.com",
    )
    detail = adapter.parse_detail_html(
        html,
        url="https://www.36kr.com/p/3919391204415360",
    )
    assert "世界模型" in detail.title
    assert len(detail.content_text) > 500
    assert len(detail.images) >= 1
    assert detail.published_at is not None
    assert detail.summary
