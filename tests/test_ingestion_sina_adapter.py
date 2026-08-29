"""Sina tech adapter fixture tests."""
from pathlib import Path

from services.ingestion.adapters.sina_tech_news import SinaTechNewsAdapter

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sina"


def test_parse_detail_tech_sina_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    adapter = SinaTechNewsAdapter(source_id="sina_tech", base_url="https://tech.sina.cn")
    detail = adapter.parse_detail_html(
        html,
        url="https://tech.sina.cn/2026-08-28/detail-inipvmmz4798526.d.html",
    )
    assert "宇树机器人" in detail.title
    assert len(detail.content_text) > 500
    assert detail.published_at is not None


def test_parse_detail_k_sina_uses_json_ld_title():
    html = (FIXTURE_DIR / "detail_k_sina.html").read_text(encoding="utf-8")
    adapter = SinaTechNewsAdapter(source_id="sina_tech", base_url="https://k.sina.cn")
    detail = adapter.parse_detail_html(
        html,
        url="https://k.sina.cn/article_1496814565_m593793e5033024crg.html",
    )
    assert "色盲图" in detail.title or len(detail.title) >= 8
    assert detail.summary
