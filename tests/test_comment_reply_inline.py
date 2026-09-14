"""Tests for inline comment reply (active-feed path and orchestrator)."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.wechat_channels_audience_reply import (
    activate_wechat_post_session,
    reply_wechat_audience_comment_on_active_feed,
)
from services.publishing.comment_reply.types import InboundComment, PostCommentSession


def _session(*, feed_active: bool = True) -> PostCommentSession:
    return PostCommentSession(
        platform_post_id="export/abc",
        post_title="测试标题",
        hub_feed_text="测试侧栏文案",
        feed_match_spec={"required": ["测试侧栏文案"], "preferred": []},
        feed_active=feed_active,
        post_context_json='{"hub_feed_text":"测试侧栏文案"}',
    )


def test_reply_on_active_feed_does_not_navigate_or_activate():
    page = MagicMock()
    comment = InboundComment(
        platform_post_id="export/abc",
        platform_comment_id="cmt-1",
        author_name="路人",
        content="讲得很好",
        commented_at=datetime.utcnow(),
    )
    with (
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._navigate_comment_hub"
        ) as navigate,
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._ensure_feed_active"
        ) as ensure_active,
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._click_reply_for_comment",
            return_value={"clicked": True},
        ),
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._find_reply_input"
        ) as find_input,
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply.human_fill"
        ),
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply.human_pause"
        ),
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply.human_click"
        ),
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._dismiss_wechat_tip"
        ),
    ):
        input_loc = MagicMock()
        input_loc.count.return_value = 1
        input_loc.is_visible.return_value = True
        find_input.return_value = input_loc
        submit = MagicMock()
        submit.count.return_value = 1
        submit.is_visible.return_value = True
        page.locator.return_value.first = submit

        result = reply_wechat_audience_comment_on_active_feed(
            page,
            session=_session(),
            comment=comment,
            reply_text="感谢支持，欢迎继续交流",
        )

    assert result.success is True
    navigate.assert_not_called()
    ensure_active.assert_not_called()


def test_reply_on_active_feed_fails_when_session_not_active():
    page = MagicMock()
    comment = InboundComment(
        platform_post_id="export/abc",
        platform_comment_id="cmt-1",
        author_name="路人",
        content="讲得很好",
        commented_at=datetime.utcnow(),
    )
    result = reply_wechat_audience_comment_on_active_feed(
        page,
        session=_session(feed_active=False),
        comment=comment,
        reply_text="感谢支持，欢迎继续交流",
    )
    assert result.success is False
    assert result.error_message == "feed_not_active"


def test_activate_wechat_post_session_sets_feed_active():
    page = MagicMock()
    post_row = {"export_id": "export/abc", "title": "测试标题"}
    with (
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._navigate_comment_hub"
        ),
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._ensure_feed_active",
            return_value=True,
        ),
        patch(
            "services.publishing.adapters.wechat_channels_audience_reply._read_active_feed_text",
            return_value="测试侧栏文案",
        ),
    ):
        session = activate_wechat_post_session(
            page,
            post_row=post_row,
            feed_match_spec={"required": ["测试侧栏文案"], "preferred": []},
        )
    assert session.feed_active is True
    assert session.platform_post_id == "export/abc"
    assert session.hub_feed_text == "测试侧栏文案"


def test_scan_account_inline_replies_in_same_browser_session():
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

    account = SimpleNamespace(
        id="acc-1",
        platform="wechat_channels",
        status="active",
        nickname="小牛聊AI",
        session_path="data/sessions/wechat.json",
    )
    post_row = {"export_id": "export/abc", "title": "测试", "comment_count": 2}
    comments = [
        InboundComment(
            platform_post_id="export/abc",
            platform_comment_id="c1",
            author_name="甲",
            content="第一条评论内容足够长",
            commented_at=datetime.utcnow(),
        ),
        InboundComment(
            platform_post_id="export/abc",
            platform_comment_id="c2",
            author_name="乙",
            content="第二条评论内容足够长",
            commented_at=datetime.utcnow(),
        ),
    ]
    session = _session()
    browser_ctx = MagicMock()
    browser_ctx.page = MagicMock()

    with (
        patch(
            "services.publishing.comment_reply.orchestrator.load_comment_reply_config",
            return_value={
                "effective_mode": "inline",
                "lookback_hours": 48,
                "max_scan_posts": 10,
                "max_replies_per_run": 10,
                "max_replies_per_post": 10,
                "pause_between_replies_sec": 0,
                "reply_min_length": 5,
                "reply_max_length": 50,
                "retry_max": 3,
            },
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.merge_post_backlog",
            side_effect=lambda session, **kwargs: kwargs["api_comments"],
        ),
        patch(
            "services.publishing.comment_reply.orchestrator._navigate_comment_hub",
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.open_adapter_browser",
            return_value=MagicMock(__enter__=lambda s: browser_ctx, __exit__=lambda *a: None),
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.fetch_wechat_post_rows",
            return_value=[post_row],
        ) as fetch_posts,
        patch(
            "services.publishing.comment_reply.orchestrator.activate_wechat_post_session",
            return_value=session,
        ) as activate,
        patch(
            "services.publishing.comment_reply.orchestrator.fetch_wechat_comments_for_post",
            return_value=comments,
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.resolve_inline_reply_text",
            return_value="感谢你的留言，我们会继续分享",
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.reply_wechat_audience_comment_on_active_feed",
            return_value=CommentResult(success=True, comment_id="c1"),
        ) as reply_active,
        patch(
            "services.publishing.comment_reply.orchestrator.scan_account_comments"
        ) as scan_batch,
        patch("services.publishing.comment_reply.orchestrator.time.sleep"),
    ):
        factory = MagicMock()
        db = MagicMock()
        factory.return_value.__enter__ = lambda s: db
        factory.return_value.__exit__ = lambda *a: None
        db.get.return_value = account
        db.query.return_value.filter_by.return_value.all.return_value = []
        db.query.return_value.filter_by.return_value.first.return_value = None

        orchestrator = CommentReplyOrchestrator(factory)
        summary = orchestrator.scan_account_inline("acc-1")

    scan_batch.assert_not_called()
    fetch_posts.assert_called_once()
    assert activate.call_count == 1
    assert reply_active.call_count == 2
    assert summary.auto_sent == 2
    assert summary.posts_scanned == 1


def test_scan_account_inline_sends_pending_approval_without_regenerating():
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator
    from src.db.models.publishing import CommentInbox

    account = SimpleNamespace(
        id="acc-1",
        platform="wechat_channels",
        status="active",
        nickname="小牛聊AI",
        session_path="data/sessions/wechat.json",
    )
    post_row = {"export_id": "export/abc", "title": "测试", "comment_count": 1}
    comments = [
        InboundComment(
            platform_post_id="export/abc",
            platform_comment_id="c1",
            author_name="甲",
            content="第一条评论内容足够长",
            commented_at=datetime.utcnow(),
        ),
    ]
    pending = CommentInbox(
        id="inbox-1",
        account_id="acc-1",
        platform="wechat_channels",
        platform_post_id="export/abc",
        platform_comment_id="c1",
        content="第一条评论内容足够长",
        status="pending_approval",
        reply_text="已生成待发送回复",
    )
    session = _session()
    browser_ctx = MagicMock()
    browser_ctx.page = MagicMock()

    with (
        patch(
            "services.publishing.comment_reply.orchestrator.load_comment_reply_config",
            return_value={
                "lookback_hours": 48,
                "max_scan_posts": 10,
                "max_replies_per_run": 10,
                "max_replies_per_post": 10,
                "pause_between_replies_sec": 0,
                "reply_min_length": 5,
                "reply_max_length": 50,
                "retry_max": 3,
            },
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.merge_post_backlog",
            side_effect=lambda session, **kwargs: kwargs["api_comments"],
        ),
        patch("services.publishing.comment_reply.orchestrator._navigate_comment_hub"),
        patch(
            "services.publishing.comment_reply.orchestrator.open_adapter_browser",
            return_value=MagicMock(__enter__=lambda s: browser_ctx, __exit__=lambda *a: None),
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.fetch_wechat_post_rows",
            return_value=[post_row],
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.activate_wechat_post_session",
            return_value=session,
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.fetch_wechat_comments_for_post",
            return_value=comments,
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.resolve_inline_reply_text",
            return_value="已生成待发送回复",
        ) as resolve_reply,
        patch(
            "services.publishing.comment_reply.orchestrator.reply_wechat_audience_comment_on_active_feed",
            return_value=CommentResult(success=True, comment_id="c1"),
        ) as reply_active,
        patch("services.publishing.comment_reply.orchestrator.time.sleep"),
    ):
        factory = MagicMock()
        db = MagicMock()
        factory.return_value.__enter__ = lambda s: db
        factory.return_value.__exit__ = lambda *a: None
        db.get.return_value = account
        db.query.return_value.filter_by.return_value.all.return_value = []
        db.query.return_value.filter_by.return_value.first.return_value = pending

        orchestrator = CommentReplyOrchestrator(factory)
        summary = orchestrator.scan_account_inline("acc-1")

    resolve_reply.assert_called_once()
    reply_active.assert_called_once()
    assert pending.status == "replied"
    assert summary.auto_sent == 1


def test_send_inbox_item_skips_retry_when_platform_already_replied():
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator
    from src.db.models.publishing import CommentInbox, PublisherAccount

    row = CommentInbox(
        id="inbox-1",
        account_id="acc-1",
        platform="wechat_channels",
        platform_post_id="export/abc",
        platform_comment_id="c1",
        content="观众评论内容足够长",
        status="failed",
        reply_text="感谢支持我们会继续分享",
        retry_count=1,
    )
    account = PublisherAccount(
        id="acc-1",
        platform="wechat_channels",
        nickname="小牛聊AI",
        session_path="data/sessions/wechat.json",
        status="active",
    )
    browser_ctx = MagicMock()
    browser_ctx.page = MagicMock()
    already_replied = InboundComment(
        platform_post_id="export/abc",
        platform_comment_id="c1",
        author_name="路人",
        content="观众评论内容足够长",
        commented_at=datetime.utcnow(),
        already_replied_by_author=True,
    )

    with (
        patch(
            "services.publishing.comment_reply.orchestrator.load_comment_reply_config",
            return_value={"reply_min_length": 5, "reply_max_length": 50},
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.open_adapter_browser",
            return_value=MagicMock(__enter__=lambda s: browser_ctx, __exit__=lambda *a: None),
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.fetch_wechat_comments_for_post",
            return_value=[already_replied],
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.reply_audience_comment"
        ) as reply_full,
    ):
        factory = MagicMock()
        db = MagicMock()
        factory.return_value.__enter__ = lambda s: db
        factory.return_value.__exit__ = lambda *a: None

        def _get(model, pk):
            if model is CommentInbox and pk == "inbox-1":
                return row
            if model is PublisherAccount:
                return account
            return None

        db.get.side_effect = _get

        orchestrator = CommentReplyOrchestrator(factory)
        result = orchestrator._send_inbox_item("inbox-1")

    reply_full.assert_not_called()
    assert result["success"] is False
    assert row.status == "skipped"
    assert row.skip_reason == "already_replied"
