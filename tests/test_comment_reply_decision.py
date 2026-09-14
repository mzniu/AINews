"""Tests for comment reply process decisions (inline / retry idempotency)."""
from datetime import datetime, timedelta

from services.publishing.comment_reply.decision import ProcessDecision, should_process_comment
from services.publishing.comment_reply.types import InboundComment


def _comment(**kwargs) -> InboundComment:
    defaults = {
        "platform_post_id": "export/x",
        "platform_comment_id": "c1",
        "author_name": "路人",
        "content": "说得很有道理",
        "commented_at": datetime.utcnow(),
    }
    defaults.update(kwargs)
    return InboundComment(**defaults)


class _FakeInbox:
    def __init__(self, status: str) -> None:
        self.status = status


def test_should_not_process_when_inbox_already_replied():
    decision = should_process_comment(
        _comment(),
        existing_row=_FakeInbox("replied"),
        account_nickname="小牛聊AI",
        author_first_comments=set(),
    )
    assert decision == ProcessDecision(process=False, reason="already_recorded")


def test_should_not_process_when_platform_already_replied():
    decision = should_process_comment(
        _comment(already_replied_by_author=True),
        existing_row=None,
        account_nickname="小牛聊AI",
        author_first_comments=set(),
    )
    assert decision == ProcessDecision(
        process=False,
        reason="already_replied",
        record_skip=True,
    )


def test_should_process_fresh_comment():
    decision = should_process_comment(
        _comment(),
        existing_row=None,
        account_nickname="小牛聊AI",
        author_first_comments=set(),
    )
    assert decision == ProcessDecision(process=True, reason=None)


def test_should_skip_too_old_comment():
    old = datetime.utcnow() - timedelta(hours=72)
    decision = should_process_comment(
        _comment(commented_at=old),
        existing_row=None,
        account_nickname="小牛聊AI",
        author_first_comments=set(),
        lookback=datetime.utcnow() - timedelta(hours=48),
    )
    assert decision == ProcessDecision(process=False, reason="too_old", record_skip=True)


def test_retry_should_not_send_when_platform_already_replied():
    decision = should_process_comment(
        _comment(already_replied_by_author=True),
        existing_row=_FakeInbox("failed"),
        account_nickname="小牛聊AI",
        author_first_comments=set(),
        intent="retry",
    )
    assert decision == ProcessDecision(
        process=False,
        reason="already_replied",
        record_skip=False,
        update_status="skipped",
    )


def test_retry_should_send_when_failed_and_not_replied_on_platform():
    decision = should_process_comment(
        _comment(),
        existing_row=_FakeInbox("failed"),
        account_nickname="小牛聊AI",
        author_first_comments=set(),
        intent="retry",
    )
    assert decision == ProcessDecision(process=True, reason=None)


def test_inline_should_send_pending_approval():
    decision = should_process_comment(
        _comment(),
        existing_row=_FakeInbox("pending_approval"),
        account_nickname="小牛聊AI",
        author_first_comments=set(),
        intent="inline",
    )
    assert decision == ProcessDecision(process=True, reason=None)


def test_inline_should_retry_failed_when_under_limit():
    row = _FakeInbox("failed")
    row.retry_count = 1
    decision = should_process_comment(
        _comment(),
        existing_row=row,
        account_nickname="小牛聊AI",
        author_first_comments=set(),
        intent="inline",
        retry_max=3,
    )
    assert decision == ProcessDecision(process=True, reason=None)


def test_inline_should_not_retry_failed_when_exhausted():
    row = _FakeInbox("failed")
    row.retry_count = 3
    decision = should_process_comment(
        _comment(),
        existing_row=row,
        account_nickname="小牛聊AI",
        author_first_comments=set(),
        intent="inline",
        retry_max=3,
    )
    assert decision == ProcessDecision(process=False, reason="retry_exhausted")
