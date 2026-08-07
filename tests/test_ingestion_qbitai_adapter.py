"""量子位 adapter fixture tests."""
from pathlib import Path

from services.ingestion.adapters.qbitai_news import QbitaiNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "qbitai"


def test_parse_list_page_from_fixture():
    html = (FIXTURE_DIR / "list_home.html").read_text(encoding="utf-8")
    adapter = QbitaiNewsAdapter(
        source_id="qbitai",
        base_url="https://www.qbitai.com",
    )
    items = adapter.parse_list_html(html)
    assert len(items) >= 8
    first = items[0]
    assert "/2026/" in first.url
    assert len(first.title) >= 4
    assert first.theme == "AI"


def test_parse_detail_page_from_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    adapter = QbitaiNewsAdapter(
        source_id="qbitai",
        base_url="https://www.qbitai.com",
    )
    detail = adapter.parse_detail_html(
        html,
        url="https://www.qbitai.com/2026/07/464169.html",
    )
    assert "米哈游" in detail.title
    assert len(detail.content_text) > 500
    assert len(detail.images) >= 1
    assert detail.author == "鹭羽"
    assert detail.published_at is not None
    assert detail.summary
