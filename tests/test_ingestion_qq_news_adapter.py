"""Tencent News adapter parsing from JSON/HTML fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from services.ingestion.adapters.base import ArticleRef
from services.ingestion.adapters.qq_news import QqNewsAdapter, extract_window_data

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "qq_news"


def _adapter() -> QqNewsAdapter:
    return QqNewsAdapter(
        source_id="qq_news_fx",
        base_url="https://news.qq.com",
        channel_id="news_news_fx",
        list_referer="https://news.qq.com/ch/fx",
    )


def test_parse_list_payload_from_fixture():
    payload = json.loads((FIXTURE_DIR / "list_fx.json").read_text(encoding="utf-8"))
    adapter = _adapter()
    items = adapter.parse_list_payload(payload)
    assert len(items) >= 8
    first = items[0]
    assert "news.qq.com" in first.url or "inews.qq.com" in first.url
    assert len(first.title) >= 6
    assert first.theme == "财经"
    assert first.extra.get("article_id")
    assert all("V" not in (item.extra.get("article_id") or "")[8:9] for item in items)


def test_parse_detail_page_from_fixture():
    html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    adapter = _adapter()
    detail = adapter.parse_detail_html(
        html,
        url="https://news.qq.com/rain/a/20260810A0BO7100",
    )
    assert "Muse Glimmer" in detail.title or "Meta" in detail.title
    assert len(detail.content_text) > 500
    assert detail.summary
    assert detail.published_at is not None
    assert detail.author


def test_parse_detail_multi_image_from_fixture():
    html = (FIXTURE_DIR / "detail_multi_img.html").read_text(encoding="utf-8")
    adapter = _adapter()
    detail = adapter.parse_detail_html(
        html,
        url="https://view.inews.qq.com/a/20260810A04WOP00",
    )
    assert "硅谷" in detail.title or "Agent" in detail.title
    assert len(detail.images) >= 7
    assert all("gtimg.com" in image for image in detail.images)
    assert detail.cover_image_url == detail.images[0]


def test_skips_video_items():
    adapter = _adapter()
    payload = {
        "data": [
            {
                "id": "wrap",
                "sub_item": [
                    {
                        "id": "20260810V07HLW00",
                        "articletype": "56",
                        "title": "视频稿",
                        "link_info": {"url": "https://news.qq.com/rain/a/20260810V07HLW00"},
                    },
                    {
                        "id": "20260810A0BO7100",
                        "articletype": "0",
                        "title": "图文稿标题足够长",
                        "publish_time": "2026-08-10 19:43:37",
                        "link_info": {"url": "https://news.qq.com/rain/a/20260810A0BO7100"},
                    },
                ],
            }
        ]
    }
    items = adapter.parse_list_payload(payload)
    assert len(items) == 1
    assert items[0].extra["article_id"] == "20260810A0BO7100"


def test_extract_window_data_handles_nested_braces_and_js_terminator():
    html = """
    <script>
    window.DATA = {"title":"含};的标题","originContent":{"text":"正文};还在继续"}};
    </script>
    """
    data = extract_window_data(html)
    assert data is not None
    assert data["title"] == "含};的标题"
    assert data["originContent"]["text"] == "正文};还在继续"


def test_extract_window_data_without_semicolon_before_script_end():
    html = '<script>window.DATA = {"title":"无分号稿","originContent":{"text":"ok"}}</script>'
    data = extract_window_data(html)
    assert data is not None
    assert data["title"] == "无分号稿"


def test_list_request_headers_include_origin():
    headers = _adapter()._headers()
    assert headers["Origin"] == "https://news.qq.com"
    assert headers["Referer"] == "https://news.qq.com/ch/fx"


def test_fetch_list_payload_retries_business_error(monkeypatch):
    adapter = _adapter()
    payload = json.loads((FIXTURE_DIR / "list_fx.json").read_text(encoding="utf-8"))
    calls = {"n": 0}

    def fake_post(_url, **_kwargs):
        calls["n"] += 1
        response = MagicMock()
        if calls["n"] == 1:
            response.json.return_value = {"code": 1, "message": "busy"}
        else:
            response.json.return_value = payload
        return response

    monkeypatch.setattr("services.ingestion.adapters.qq_news.post_json", fake_post)
    monkeypatch.setattr("services.ingestion.adapters.qq_news.time.sleep", lambda *_args, **_kwargs: None)
    items = adapter.discover_list("https://news.qq.com/ch/fx?page=0")
    assert calls["n"] == 2
    assert len(items) >= 8


def test_fetch_detail_falls_back_to_original_url(monkeypatch):
    adapter = _adapter()
    empty_html = "<html><body>access denied</body></html>"
    good_html = (FIXTURE_DIR / "detail_sample.html").read_text(encoding="utf-8")
    seen: list[str] = []

    def fake_fetch(url: str) -> str:
        seen.append(url)
        if "/rain/a/" in url:
            return empty_html
        return good_html

    monkeypatch.setattr(adapter, "fetch_html", fake_fetch)
    ref = ArticleRef(
        url="https://view.inews.qq.com/a/20260810A0BO7100",
        title="Meta开源",
        extra={"article_id": "20260810A0BO7100"},
    )
    detail = adapter.fetch_detail(ref)
    assert any("/rain/a/" in url for url in seen)
    assert any("inews.qq.com" in url for url in seen)
    assert "Muse Glimmer" in detail.title or "Meta" in detail.title
    assert len(detail.content_text) > 500
