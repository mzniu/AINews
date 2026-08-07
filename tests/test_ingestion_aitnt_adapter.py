"""AITNT adapter parsing from HTML fixtures."""
from pathlib import Path

from services.ingestion.adapters.aitnt_news import AitntNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "aitnt"


def test_parse_list_page_from_fixture():
    html = (FIXTURE_DIR / "list_index1.html").read_text(encoding="utf-8")
    adapter = AitntNewsAdapter(
        source_id="aitnt_travel",
        base_url="http://travel.aitntnews.com",
    )
    items = adapter.parse_list_html(html)
    assert len(items) >= 10
    first = items[0]
    assert "newId=27818" in first.url
    assert "盘古" in first.title
    assert first.summary
    assert first.theme == "AI资讯"
    assert first.published_at is not None
    assert first.view_count == 8706


def test_parse_detail_page_from_fixture():
    html = (FIXTURE_DIR / "detail_27818.html").read_text(encoding="utf-8")
    adapter = AitntNewsAdapter(
        source_id="aitnt_travel",
        base_url="http://travel.aitntnews.com",
    )
    detail = adapter.parse_detail_html(
        html,
        url="http://travel.aitntnews.com/newDetail.html?newId=27818",
    )
    assert "openPangu-2.0-Pro" in detail.title
    assert len(detail.content_text) > 200
    assert len(detail.images) >= 2
    assert any("pictures" in img for img in detail.images)
    assert detail.view_count == 8706
