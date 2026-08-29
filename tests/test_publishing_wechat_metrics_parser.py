"""Tests for WeChat Channels metrics row parsing."""
from services.publishing.metrics.adapters.wechat_channels import (
    build_wechat_metrics_items_from_rows,
    parse_wechat_post_list_payload,
)


def test_build_wechat_metrics_items_from_rows():
    rows = [
        {
            "export_id": "export123",
            "title": "视频号作品",
            "view_count": "1500",
            "like_count": "32",
            "comment_count": "5",
            "share_count": "2",
        }
    ]
    items = build_wechat_metrics_items_from_rows(rows)
    assert len(items) == 1
    item = items[0]
    assert item.platform_post_id == "export123"
    assert item.view_count == 1500
    assert item.share_count == 2


def test_parse_wechat_post_list_payload():
    payload = {
        "errCode": 0,
        "data": {
            "list": [
                {
                    "objectId": "export/UzFfBgAAtest",
                    "createTime": 1786374192,
                    "readCount": 542,
                    "likeCount": 3,
                    "commentCount": 1,
                    "forwardCount": 2,
                    "favCount": 4,
                    "followCount": 6,
                    "fullPlayRate": 0.31,
                    "play3sRate": 0.55,
                    "avgPlayTimeMs": 7200,
                    "clickProfileCount": 3,
                    "desc": {
                        "shortTitle": [{"shortTitle": "炸裂？Claude挖角遭秒拒"}],
                        "description": "",
                    },
                }
            ],
            "continueFlag": True,
            "totalCount": 1,
        },
    }
    rows = parse_wechat_post_list_payload(payload)
    assert len(rows) == 1
    assert rows[0]["export_id"] == "export/UzFfBgAAtest"
    assert rows[0]["title"] == "炸裂？Claude挖角遭秒拒"
    assert rows[0]["view_count"] == 542
    assert rows[0]["follow_count"] == 6
    assert rows[0]["completion_rate"] == 0.31
    assert rows[0]["play_3s_rate"] == 0.55
    assert rows[0]["avg_watch_sec"] == 7200
    assert rows[0]["profile_click_count"] == 3


def test_parse_wechat_post_list_payload_rejects_logged_out():
    payload = {"errCode": 300334, "errMsg": "login fail", "data": {}}
    assert parse_wechat_post_list_payload(payload) == []
