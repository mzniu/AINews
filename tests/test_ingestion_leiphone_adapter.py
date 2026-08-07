"""雷锋网 AI adapter fixture tests."""
from pathlib import Path

from services.ingestion.adapters.leiphone_news import LeiphoneNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "leiphone"


def test_parse_list_page_from_fixture():
    html = (FIXTURE_DIR / "list_ai.html").read_text(encoding="utf-8")
    adapter = LeiphoneNewsAdapter(
        source_id="leiphone_ai",
        base_url="https://www.leiphone.com",
    )
    items = adapter.parse_list_html(html)
    assert len(items) >= 10
    first = items[0]
    assert "/category/ai/" in first.url
    assert "Kimi" in first.title or len(first.title) >= 8
    assert first.theme == "AI"


def test_parse_detail_page_from_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    adapter = LeiphoneNewsAdapter(
        source_id="leiphone_ai",
        base_url="https://www.leiphone.com",
    )
    detail = adapter.parse_detail_html(
        html,
        url="https://www.leiphone.com/category/ai/mER69AfKN23gn4Yt.html",
    )
    assert "Kimi" in detail.title
    assert len(detail.content_text) > 500
    assert len(detail.images) >= 1
    assert detail.author == "樊天骄"
    assert detail.published_at is not None
    assert detail.summary
