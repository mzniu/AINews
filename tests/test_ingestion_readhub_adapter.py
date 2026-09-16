"""Readhub topic adapter fixture tests."""
from pathlib import Path

from services.ingestion.adapters.readhub_news import ReadhubNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "readhub"


def test_parse_detail_readhub_topic_fixture():
    html = (FIXTURE_DIR / "topic_sample.html").read_text(encoding="utf-8")
    adapter = ReadhubNewsAdapter(source_id="readhub_ai", base_url="https://readhub.cn")
    detail = adapter.parse_detail_html(html, url="https://readhub.cn/topic/8vy479AZCbr")
    assert len(detail.title) >= 8
    assert len(detail.content_text) > 80
    assert "专业版" not in detail.content_text
