"""Tests for Douyin inline comment reply orchestration."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.publishing.adapters.base import CommentResult
from services.publishing.comment_reply.types import InboundComment, PostCommentSession


def test_scan_douyin_inline_replies_multiple_comments():
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

    account = SimpleNamespace(
        id="acc-dy",
        platform="douyin",
        status="active",
        nickname="小牛聊AI",
        session_path="data/sessions/douyin.json",
    )
    post_row = {"video_id": "7673873560674290944", "title": "测试", "comment_count": 2}
    comments = [
        InboundComment(
            platform_post_id="7673873560674290944",
            platform_comment_id="c1",
            author_name="甲",
            content="第一条评论内容足够长",
            commented_at=datetime.utcnow(),
        ),
        InboundComment(
            platform_post_id="7673873560674290944",
            platform_comment_id="c2",
            author_name="乙",
            content="第二条评论内容足够长",
            commented_at=datetime.utcnow(),
        ),
    ]
    session = PostCommentSession(
        platform_post_id="7673873560674290944",
        post_title="测试",
        hub_feed_text=None,
        feed_match_spec=None,
        feed_active=True,
        post_context_json=None,
    )
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
        patch(
            "services.publishing.comment_reply.orchestrator.open_adapter_browser",
            return_value=MagicMock(__enter__=lambda s: browser_ctx, __exit__=lambda *a: None),
        ),
        patch(
            "services.publishing.adapters.douyin_audience_reply._navigate_comment_hub",
        ),
        patch(
            "services.publishing.adapters.douyin_audience_reply.scan_douyin_post_rows",
            return_value=[post_row],
        ),
        patch(
            "services.publishing.adapters.douyin_audience_reply.activate_douyin_post_session",
            return_value=session,
        ),
        patch(
            "services.publishing.adapters.douyin_audience_reply.fetch_douyin_comments_for_post",
            return_value=comments,
        ),
        patch(
            "services.publishing.comment_reply.orchestrator.resolve_inline_reply_text",
            return_value="感谢你的留言我们会继续分享",
        ),
        patch(
            "services.publishing.adapters.douyin_audience_reply.reply_douyin_audience_comment_on_active_feed",
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
        db.query.return_value.filter_by.return_value.first.return_value = None

        orchestrator = CommentReplyOrchestrator(factory)
        summary = orchestrator.scan_douyin_inline("acc-dy")

    assert reply_active.call_count == 2
    assert summary.auto_sent == 2
    assert summary.posts_scanned == 1
