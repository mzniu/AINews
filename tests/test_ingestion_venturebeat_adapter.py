"""VentureBeat AI adapter fixture tests."""
from __future__ import annotations

from pathlib import Path

from services.ingestion.adapters.base import ArticleRef
from services.ingestion.adapters.venturebeat_news import VenturebeatNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "venturebeat"


def _adapter() -> VenturebeatNewsAdapter:
    return VenturebeatNewsAdapter(
        source_id="venturebeat_ai",
        base_url="https://venturebeat.com",
        list_referer="https://venturebeat.com/category/ai/feed/",
    )


def test_parse_list_rss_from_fixture():
    xml = (FIXTURE_DIR / "list_ai.xml").read_text(encoding="utf-8")
    items = _adapter().parse_list_xml(xml)
    assert len(items) >= 3
    first = items[0]
    assert "venturebeat.com" in first.url
    assert "Lead Analyst" in first.title
    assert first.theme == "AI"
    assert first.summary
    assert "Rob Strechay" in (first.summary or "")
    assert first.cover_image_url
    assert "ctfassets.net" in first.cover_image_url
    assert first.published_at is not None
    assert first.published_at.year == 2026
    assert first.published_at.hour == 22
    assert first.extra.get("author") == "Matt Marshall"
    assert any("Google" in item.title for item in items)


def test_fetch_detail_uses_rss_body_without_network():
    xml = (FIXTURE_DIR / "list_ai.xml").read_text(encoding="utf-8")
    adapter = _adapter()
    ref = adapter.parse_list_xml(xml)[0]
    detail = adapter.fetch_detail(ref)
    assert "Lead Analyst" in detail.title
    assert "Rob Strechay" in detail.content_text
    assert len(detail.content_text) > 500
    assert detail.author == "Matt Marshall"
    assert detail.cover_image_url
    assert detail.theme == "AI"


def test_parse_detail_html_from_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    detail = _adapter().parse_detail_html(
        html,
        url="https://venturebeat.com/ai/venturebeat-names-rob-strechay-as-its-first-lead-analyst-expanding-its-enterprise-ai-research-push",
    )
    assert "Lead Analyst" in detail.title
    assert "theCUBE" in detail.content_text
    assert detail.author == "Matt Marshall"
    assert detail.images
    assert detail.cover_image_url


def test_discover_list_fetches_rss(monkeypatch):
    adapter = _adapter()
    xml = (FIXTURE_DIR / "list_ai.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(adapter, "fetch_list_xml", lambda _url: xml)
    items = adapter.discover_list("https://venturebeat.com/category/ai/feed/")
    assert len(items) >= 3


def test_fetch_detail_falls_back_to_html(monkeypatch):
    adapter = _adapter()
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    monkeypatch.setattr(adapter, "fetch_html", lambda _url: html)
    ref = ArticleRef(
        url="https://venturebeat.com/ai/venturebeat-names-rob-strechay-as-its-first-lead-analyst-expanding-its-enterprise-ai-research-push",
        title="placeholder",
        theme="AI",
    )
    detail = adapter.fetch_detail(ref)
    assert "Lead Analyst" in detail.title
    assert "theCUBE" in detail.content_text
