"""IT之家 IT 频道 adapter fixture tests."""
from __future__ import annotations

import json
from pathlib import Path

from services.ingestion.adapters.ithome_news import IthomeNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ithome"


def _adapter() -> IthomeNewsAdapter:
    return IthomeNewsAdapter(
        source_id="ithome_it",
        base_url="https://it.ithome.com",
    )


def test_parse_list_page_from_fixture():
    html = (FIXTURE_DIR / "list_it.html").read_text(encoding="utf-8")
    items = _adapter().parse_list_html(html)
    assert len(items) >= 4
    first = items[0]
    assert "/0/" in first.url
    assert first.url.endswith(".htm")
    assert "吴泳铭" in first.title or len(first.title) >= 8
    assert first.theme == "IT"
    assert first.summary
    assert first.cover_image_url
    assert first.published_at is not None


def test_parse_load_more_html_from_fixture():
    payload = json.loads((FIXTURE_DIR / "list_more.json").read_text(encoding="utf-8"))
    html = payload["content"]["html"]
    items = _adapter().parse_list_html(html)
    assert len(items) >= 3
    assert any("992/322.htm" in item.url for item in items)
    assert all(item.theme == "IT" for item in items)


def test_parse_detail_page_from_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    detail = _adapter().parse_detail_html(
        html,
        url="https://www.ithome.com/0/992/380.htm",
    )
    assert "吴泳铭" in detail.title
    assert "平头哥" in detail.content_text
    assert len(detail.content_text) > 200
    assert "相关文章" not in detail.content_text
    assert detail.author == "清源"
    assert detail.published_at is not None
    assert detail.published_at.year == 2026
    assert detail.summary
    assert detail.images
    assert all("t.png" not in image for image in detail.images)
    assert "newsuploadfiles" in (detail.cover_image_url or "")
