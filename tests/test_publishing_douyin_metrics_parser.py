"""Tests for Douyin metrics row parsing."""
from services.publishing.metrics.adapters.douyin import (
    build_douyin_metrics_items_from_rows,
    parse_douyin_work_list_page_info,
    parse_douyin_work_list_payload,
)


def test_build_douyin_metrics_items_from_rows():
    rows = [
        {
            "video_id": "7123456789012345678",
            "title": "AI 资讯",
            "view_count": "2.3万",
            "like_count": "120",
            "comment_count": "8",
            "share_count": "3",
        }
    ]
    items = build_douyin_metrics_items_from_rows(rows)
    assert len(items) == 1
    item = items[0]
    assert item.platform_post_id == "7123456789012345678"
    assert item.view_count == 23000
    assert item.like_count == 120
    assert "douyin.com/video/" in (item.post_url or "")


def test_parse_douyin_work_list_payload_new_format():
    payload = {
        "data": {
            "work_list": [
                {
                    "aweme_id": "7123456789012345678",
                    "desc": "AI 资讯",
                    "create_time": 1723334400,
                    "statistics": {
                        "play_count": 23000,
                        "digg_count": 120,
                        "comment_count": 8,
                        "share_count": 3,
                        "collect_count": 9,
                        "follow_count": 4,
                        "play_3s_rate": 0.41,
                        "finish_rate": 0.22,
                        "avg_play_duration": 8500,
                        "homepage_click": 11,
                    },
                }
            ]
        }
    }
    rows = parse_douyin_work_list_payload(payload)
    assert len(rows) == 1
    assert rows[0]["video_id"] == "7123456789012345678"
    assert rows[0]["title"] == "AI 资讯"
    assert rows[0]["view_count"] == 23000
    assert rows[0]["follow_count"] == 4
    assert rows[0]["play_3s_rate"] == 0.41
    assert rows[0]["completion_rate"] == 0.22
    assert rows[0]["avg_watch_sec"] == 8500
    assert rows[0]["profile_click_count"] == 11


def test_parse_douyin_work_list_payload_items_format():
    payload = {
        "status_code": 0,
        "items": [
            {
                "aweme_id": "7555555555555555555",
                "desc": "作品标题",
                "create_time": 1786373717,
                "statistics": {"play_count": 88, "digg_count": 6},
            }
        ],
        "has_more": False,
    }
    rows = parse_douyin_work_list_payload(payload)
    assert len(rows) == 1
    assert rows[0]["video_id"] == "7555555555555555555"
    assert rows[0]["view_count"] == 88


def test_parse_douyin_work_list_payload_rejects_logged_out():
    payload = {"status_code": 8, "items": [], "aweme_list": None}
    assert parse_douyin_work_list_payload(payload) == []


def test_parse_douyin_work_list_payload_legacy_aweme_list():
    payload = {
        "aweme_list": [
            {
                "aweme_id": "7999999999999999999",
                "desc": "旧接口",
                "statistics": {"play_count": 100, "digg_count": 5},
            }
        ]
    }
    rows = parse_douyin_work_list_payload(payload)
    assert len(rows) == 1
    assert rows[0]["video_id"] == "7999999999999999999"


def test_parse_douyin_work_list_page_info_cursor():
    payload = {
        "status_code": 0,
        "has_more": 1,
        "max_cursor": 1723334500000,
        "items": [{"aweme_id": "1"}],
    }
    info = parse_douyin_work_list_page_info(payload)
    assert info.has_more is True
    assert info.next_cursor == 1723334500000


def test_parse_douyin_work_list_page_info_stops_when_no_more():
    payload = {"status_code": 0, "has_more": 0, "max_cursor": 0, "items": []}
    info = parse_douyin_work_list_page_info(payload)
    assert info.has_more is False
