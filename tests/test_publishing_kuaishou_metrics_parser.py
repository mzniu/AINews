"""Tests for Kuaishou metrics row parsing."""
from services.publishing.metrics.adapters.kuaishou import (
    build_kuaishou_metrics_items_from_rows,
    parse_kuaishou_photo_list_page_info,
    parse_kuaishou_photo_list_payload,
)


def test_build_kuaishou_metrics_items_from_rows():
    rows = [
        {
            "photo_id": "3xabc123",
            "title": "快手测试",
            "view_count": "888",
            "like_count": "66",
            "comment_count": "4",
        }
    ]
    items = build_kuaishou_metrics_items_from_rows(rows)
    assert len(items) == 1
    item = items[0]
    assert item.platform_post_id == "3xabc123"
    assert item.view_count == 888
    assert "kuaishou.com" in (item.post_url or "")


def test_parse_kuaishou_photo_list_payload():
    payload = {
        "result": 1,
        "data": {
            "list": [
                {
                    "workId": "3xwmb9a2at2vezy",
                    "title": "测试作品",
                    "playCount": 182223,
                    "likeCount": 1044,
                    "commentCount": 32,
                    "shareCount": 8,
                    "followCount": 5,
                    "finishPlayRate": 0.18,
                    "play3sRate": 0.44,
                    "avgPlayDuration": 6300,
                    "uploadTime": 1772442005000,
                }
            ],
            "total": 1,
        },
    }
    rows = parse_kuaishou_photo_list_payload(payload)
    assert len(rows) == 1
    assert rows[0]["photo_id"] == "3xwmb9a2at2vezy"
    assert rows[0]["view_count"] == 182223
    assert rows[0]["follow_count"] == 5
    assert rows[0]["completion_rate"] == 0.18
    assert rows[0]["play_3s_rate"] == 0.44
    assert rows[0]["avg_watch_sec"] == 6300


def test_parse_kuaishou_photo_list_page_info_uses_total():
    payload = {
        "result": 1,
        "data": {
            "list": [{"workId": "a"}, {"workId": "b"}],
            "total": 40,
            "page": 1,
        },
    }
    info = parse_kuaishou_photo_list_page_info(payload)
    assert info.has_more is True
    assert info.next_cursor == 2


def test_parse_kuaishou_photo_list_page_info_stops_when_page_covers_total():
    payload = {
        "result": 1,
        "data": {
            "list": [{"workId": str(i)} for i in range(10)],
            "total": 30,
            "page": 2,
        },
    }
    info = parse_kuaishou_photo_list_page_info(payload)
    assert info.has_more is False


def test_parse_kuaishou_photo_list_page_info_full_page_without_total_has_more():
    payload = {
        "result": 1,
        "data": {
            "list": [{"workId": str(i)} for i in range(20)],
            "page": 1,
        },
    }
    info = parse_kuaishou_photo_list_page_info(payload)
    assert info.has_more is True
    assert info.next_cursor == 2


def test_kuaishou_fetch_post_metrics_does_not_open_another_browser(monkeypatch):
    from pathlib import Path

    from services.publishing.metrics.adapters.kuaishou import KuaishouMetricsAdapter

    def _boom(*_args, **_kwargs):
        raise AssertionError("detail fetch must not re-open a Kuaishou metrics browser")

    monkeypatch.setattr(
        "services.publishing.metrics.adapters.kuaishou.fetch_kuaishou_metrics_rows",
        _boom,
    )
    adapter = KuaishouMetricsAdapter()
    assert adapter.fetch_post_metrics(Path("unused"), platform_post_id="3xabc123") is None
