"""Tests for inline comment-reply helpers."""
from datetime import datetime, timedelta

from services.publishing.comment_reply.inline_helpers import merge_post_backlog
from services.publishing.comment_reply.types import InboundComment


class _FakeInbox:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeAccount:
    id = "acc-1"
    platform = "wechat_channels"


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, model):
        return _FakeQuery(self._rows)


def test_merge_post_backlog_appends_pending_rows_not_in_api():
    api_comments = [
        InboundComment(
            platform_post_id="export/abc",
            platform_comment_id="c1",
            author_name="A",
            content="第一条评论",
            commented_at=datetime.utcnow(),
        )
    ]
    backlog = _FakeInbox(
        account_id="acc-1",
        platform="wechat_channels",
        platform_post_id="export/abc",
        platform_comment_id="c2",
        author_name="B",
        content="待发送评论",
        commented_at=datetime.utcnow(),
        status="pending_approval",
        post_title="标题",
    )
    session = _FakeSession([backlog])
    merged = merge_post_backlog(
        session,
        account=_FakeAccount(),
        post_id="export/abc",
        api_comments=api_comments,
        lookback=datetime.utcnow() - timedelta(hours=48),
    )
    assert len(merged) == 2
    assert {item.platform_comment_id for item in merged} == {"c1", "c2"}
