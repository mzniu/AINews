"""TechCrunch AI adapter fixture tests."""
from __future__ import annotations

import json
from pathlib import Path

from services.ingestion.adapters.base import ArticleRef
from services.ingestion.adapters.techcrunch_news import TechcrunchNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "techcrunch"


def _adapter() -> TechcrunchNewsAdapter:
    return TechcrunchNewsAdapter(
        source_id="techcrunch_ai",
        base_url="https://techcrunch.com",
        category_id=577047203,
        list_referer="https://techcrunch.com/category/artificial-intelligence/",
    )


def test_parse_list_payload_from_fixture():
    payload = json.loads((FIXTURE_DIR / "list_ai.json").read_text(encoding="utf-8"))
    items = _adapter().parse_list_payload(payload)
    assert len(items) >= 3
    first = items[0]
    assert first.url.startswith("https://techcrunch.com/2026/")
    assert "Micro1" in first.title
    assert first.theme == "AI"
    assert first.summary
    assert first.cover_image_url
    assert first.published_at is not None
    assert first.published_at.year == 2026
    assert first.published_at.hour == 8
    assert first.extra.get("post_id") == 3155270
    assert any("OpenAI" in item.title for item in items)
    assert any("ChatGPT" in item.title for item in items)


def test_fetch_detail_uses_list_payload_without_network():
    payload = json.loads((FIXTURE_DIR / "list_ai.json").read_text(encoding="utf-8"))
    adapter = _adapter()
    ref = adapter.parse_list_payload(payload)[1]
    detail = adapter.fetch_detail(ref)
    assert "OpenAI" in detail.title
    assert "Anthropic" in detail.content_text
    assert len(detail.content_text) > 500
    assert "jwplayer" not in detail.content_text
    assert detail.author == "Julie Bort"
    assert detail.cover_image_url
    assert detail.theme == "AI"


def test_parse_detail_html_from_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    detail = _adapter().parse_detail_html(
        html,
        url="https://techcrunch.com/2026/08/20/openai-is-gaining-on-anthropic-with-business-users-new-data-indicates/",
    )
    assert "OpenAI" in detail.title
    assert "Ramp" in detail.content_text
    assert detail.images
    assert "openai-anthropic.jpg" in detail.images[0]
    assert detail.author == "Julie Bort"


def test_discover_list_reads_page_from_url(monkeypatch):
    adapter = _adapter()
    captured: list[int] = []

    def fake_fetch(page: int = 1) -> list:
        captured.append(page)
        return json.loads((FIXTURE_DIR / "list_ai.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(adapter, "fetch_list_payload", fake_fetch)
    items = adapter.discover_list(
        "https://techcrunch.com/category/artificial-intelligence/?page=2"
    )
    assert captured == [2]
    assert len(items) >= 3


def test_fetch_detail_falls_back_to_html(monkeypatch):
    adapter = _adapter()
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    monkeypatch.setattr(adapter, "fetch_html", lambda _url: html)
    ref = ArticleRef(
        url="https://techcrunch.com/2026/08/20/openai-is-gaining-on-anthropic-with-business-users-new-data-indicates/",
        title="placeholder",
        theme="AI",
    )
    detail = adapter.fetch_detail(ref)
    assert "OpenAI" in detail.title
    assert "Ramp" in detail.content_text
