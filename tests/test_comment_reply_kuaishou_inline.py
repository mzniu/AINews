"""Tests for Kuaishou inline comment reply tab-leak fixes."""
from unittest.mock import MagicMock, patch

from services.publishing.metrics.adapters.kuaishou import CONTENT_MANAGE_URL
from services.publishing.adapters.kuaishou_comment import (
    _fetch_comment_hub_post_rows,
    bind_kuaishou_tab_guard,
    prune_kuaishou_extra_pages,
)
from services.publishing.adapters.kuaishou_audience_reply import (
    fetch_kuaishou_comments_for_post,
    scan_kuaishou_post_rows,
)


def test_fetch_comment_hub_post_rows_does_not_open_content_manage():
    page = MagicMock()
    page.url = "https://cp.kuaishou.com/article/comment"
    page.evaluate.return_value = {
        "result": 1,
        "data": {
            "list": [
                {
                    "workId": "photo-1",
                    "title": "测试作品",
                    "commentCount": 3,
                }
            ]
        },
    }

    rows = _fetch_comment_hub_post_rows(page)

    assert len(rows) == 1
    assert rows[0]["photo_id"] == "photo-1"
    for call in page.goto.call_args_list:
        assert CONTENT_MANAGE_URL not in str(call)


def test_scan_kuaishou_post_rows_uses_comment_hub_fetch():
    page = MagicMock()
    with patch(
        "services.publishing.adapters.kuaishou_audience_reply._fetch_comment_hub_post_rows",
        return_value=[{"photo_id": "a"}, {"photo_id": "b"}],
    ) as fetch_rows:
        rows = scan_kuaishou_post_rows(page, max_posts=1)
    fetch_rows.assert_called_once_with(page)
    assert rows == [{"photo_id": "a"}]


def test_fetch_kuaishou_comments_skip_feed_select_avoids_second_click():
    page = MagicMock()
    page.evaluate.return_value = []

    with patch(
        "services.publishing.adapters.kuaishou_audience_reply._select_video_feed",
    ) as select_feed:
        fetch_kuaishou_comments_for_post(
            page,
            photo_id="photo-1",
            post_title="标题",
            account_nickname="账号",
            skip_feed_select=True,
        )

    select_feed.assert_not_called()


def test_prune_kuaishou_extra_pages_closes_stray_tabs():
    main_page = MagicMock()
    main_page.is_closed.return_value = False
    extra = MagicMock()
    extra.is_closed.return_value = False
    context = MagicMock()
    context.pages = [main_page, extra]

    prune_kuaishou_extra_pages(context, main_page)

    extra.close.assert_called_once()


def test_bind_kuaishou_tab_guard_registers_once():
    main_page = MagicMock()
    main_page.is_closed.return_value = False
    extra = MagicMock()
    extra.is_closed.return_value = False
    context = MagicMock()
    context.pages = [main_page, extra]

    bind_kuaishou_tab_guard(context, main_page)
    bind_kuaishou_tab_guard(context, main_page)

    context.on.assert_called_once()
    assert extra.close.call_count == 2


def test_prepare_kuaishou_comment_page_prunes_on_repeat():
    from services.publishing.adapters.kuaishou_comment import prepare_kuaishou_comment_page

    main_page = MagicMock()
    main_page.is_closed.return_value = False
    extra = MagicMock()
    extra.is_closed.return_value = False
    context = MagicMock()
    context.pages = [main_page, extra]

    prepare_kuaishou_comment_page(context, main_page)
    prepare_kuaishou_comment_page(context, main_page)

    assert extra.close.call_count >= 2
