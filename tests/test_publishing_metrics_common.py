"""Tests for shared metrics parsing utilities."""
from datetime import datetime

from services.publishing.metrics.adapters.common import (
    build_post_metrics_items_from_rows,
    parse_count_text,
    parse_datetime,
    parse_duration_sec,
    parse_rate_percent,
)


def test_parse_count_text_wan_and_yi():
    assert parse_count_text("1.2万") == 12000
    assert parse_count_text("1.5亿") == 150000000
    assert parse_count_text("1,234") == 1234


def test_parse_datetime_formats():
    assert parse_datetime("2026-08-10 12:00:00") == datetime(2026, 8, 10, 12, 0, 0)
    assert parse_datetime("2026-08-10") == datetime(2026, 8, 10, 0, 0, 0)


def test_parse_datetime_unix_ms_uses_utc():
    from services.publishing.metrics.adapters.common import parse_datetime

    assert parse_datetime(1772442005000) == datetime(2026, 3, 2, 9, 0, 5)


def test_collect_paginated_rows_follows_cursor_until_limit():
    from services.publishing.metrics.adapters.common import (
        MetricsPageInfo,
        collect_paginated_rows,
    )

    pages = {
        0: {
            "items": [{"video_id": "a"}, {"video_id": "b"}],
            "has_more": True,
            "max_cursor": 10,
        },
        10: {
            "items": [{"video_id": "c"}, {"video_id": "d"}],
            "has_more": True,
            "max_cursor": 20,
        },
        20: {
            "items": [{"video_id": "e"}],
            "has_more": False,
            "max_cursor": 20,
        },
    }
    calls: list[int] = []

    def fetch_page(cursor):
        calls.append(cursor)
        return pages[cursor]

    rows = collect_paginated_rows(
        fetch_page,
        parse_rows=lambda payload: payload["items"],
        parse_page_info=lambda payload: MetricsPageInfo(
            has_more=bool(payload["has_more"]),
            next_cursor=payload["max_cursor"],
        ),
        row_id=lambda row: row["video_id"],
        limit=3,
        initial_cursor=0,
    )
    assert [row["video_id"] for row in rows] == ["a", "b", "c"]
    assert calls == [0, 10]


def test_collect_paginated_rows_keeps_paging_for_needed_ids():
    from services.publishing.metrics.adapters.common import (
        MetricsPageInfo,
        collect_paginated_rows,
    )

    pages = {
        1: {"items": [{"id": "p1"}], "has_more": True, "next": 2},
        2: {"items": [{"id": "p2"}], "has_more": True, "next": 3},
        3: {"items": [{"id": "needed"}], "has_more": False, "next": 3},
    }

    rows = collect_paginated_rows(
        lambda cursor: pages[cursor],
        parse_rows=lambda payload: payload["items"],
        parse_page_info=lambda payload: MetricsPageInfo(
            has_more=bool(payload["has_more"]),
            next_cursor=payload["next"],
        ),
        row_id=lambda row: row["id"],
        limit=1,
        initial_cursor=1,
        needed_ids={"needed"},
    )
    assert [row["id"] for row in rows] == ["p1", "p2", "needed"]


def test_build_post_metrics_items_from_rows_generic():
    rows = [
        {
            "platform_post_id": "v123",
            "title": "标题",
            "view_count": "500",
            "like_count": "10",
            "post_url": "https://example.com/v123",
        }
    ]
    items = build_post_metrics_items_from_rows(rows)
    assert len(items) == 1
    assert items[0].platform_post_id == "v123"
    assert items[0].view_count == 500


def test_parse_rate_percent_accepts_ratio_percent_and_text():
    assert parse_rate_percent("35.2%") == 35.2
    assert parse_rate_percent(0.352) == 35.2
    assert parse_rate_percent(35.2) == 35.2
    assert parse_rate_percent(0) == 0.0
    assert parse_rate_percent(None) is None
    assert parse_rate_percent("—") is None


def test_parse_duration_sec_converts_milliseconds():
    assert parse_duration_sec(12.5) == 12.5
    assert parse_duration_sec(2500) == 2.5
    assert parse_duration_sec("8.0") == 8.0
    assert parse_duration_sec(None) is None


def test_build_post_metrics_items_from_rows_maps_funnel_fields():
    rows = [
        {
            "video_id": "v1",
            "follow_count": "12",
            "play_3s_rate": "0.41",
            "completion_rate": "28.5%",
            "avg_watch_sec": 9500,
            "profile_click_count": 7,
        }
    ]
    item = build_post_metrics_items_from_rows(rows, id_keys=("video_id",))[0]
    assert item.follow_count == 12
    assert item.play_3s_rate == 41.0
    assert item.completion_rate == 28.5
    assert item.avg_watch_sec == 9.5
    assert item.profile_click_count == 7
