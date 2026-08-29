"""Ifeng tech adapter fixture tests."""
from pathlib import Path

from services.ingestion.adapters.ifeng_news import IfengNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ifeng"


def test_parse_detail_ifeng_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    adapter = IfengNewsAdapter(source_id="ifeng_ai", base_url="https://tech.ifeng.com")
    detail = adapter.parse_detail_html(html, url="https://tech.ifeng.com/c/8vx4tdUz8VJ")
    assert "OpenAI" in detail.title or "智能体" in detail.title
    assert len(detail.content_text) > 500
    assert detail.published_at is not None
