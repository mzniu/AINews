"""Tests for audience comment reply P1."""
from datetime import datetime

from unittest.mock import MagicMock

from services.publishing.adapters.douyin_audience_reply import (
    _apply_douyin_reply_state,
    _author_replied_in_douyin_item,
    _author_replied_in_douyin_reply_payload,
    douyin_author_already_replied_in_thread,
    parse_douyin_comment_list_payload,
    reply_douyin_audience_comment_on_active_feed,
)
from services.publishing.adapters.kuaishou_audience_reply import parse_kuaishou_comment_list_payload
from services.publishing.adapters.wechat_channels_audience_reply import (
    build_wechat_comment_hub_needles,
    build_wechat_feed_match_spec,
    extract_wechat_copy_lines,
    normalize_wechat_export_id,
    parse_wechat_comment_list_payload,
)
from services.publishing.comment_reply.config import load_comment_reply_config
from services.publishing.comment_reply.filters import should_skip_comment
from services.publishing.comment_reply.generation import validate_reply_text
from services.publishing.comment_reply.platforms import post_id_from_row
from services.publishing.comment_reply.types import InboundComment, PostCommentSession


def test_load_comment_reply_config_defaults():
    cfg = load_comment_reply_config()
    assert cfg["mode"] in {"approve", "auto", "inline"}
    assert "wechat_channels" in cfg["platforms"]
    assert "kuaishou" in cfg["platforms"]
    assert "douyin" in cfg["platforms"]
    assert cfg["max_replies_per_run"] >= 1
    assert cfg["max_replies_per_post"] >= 1
    assert cfg["retry_max"] >= 0
    assert isinstance(cfg["enabled"], bool)


def test_load_comment_reply_config_auto_alias_maps_to_inline():
    cfg = load_comment_reply_config()
    if cfg["mode"] == "auto":
        assert cfg["effective_mode"] == "inline"
    elif cfg["mode"] == "inline":
        assert cfg["effective_mode"] == "inline"
    else:
        assert cfg["effective_mode"] == "approve"


def test_normalize_wechat_export_id():
    assert normalize_wechat_export_id("export/abc") == "export/abc"
    assert normalize_wechat_export_id("abc") == "export/abc"
    assert normalize_wechat_export_id("") == ""


def test_build_wechat_feed_match_spec_from_description():
    description = (
        "522万分，国产芯片的分水岭\n"
        "跑分破500万，实际体验能打吗？\n"
        "小牛说：小米玄戒O3发布"
    )
    spec = build_wechat_feed_match_spec(
        description,
        "小米玄戒O3跑分破五百万",
        main_line1="小米玄戒O3安兔兔跑分破500万",
        sub_title="522万分，国产芯片的分水岭",
        sub_title2="跑分破500万，实际体验能打吗？",
    )
    assert spec["required"] == ["522万分，国产芯片的分水岭"]
    assert "小米玄戒O3安兔兔跑分破500万" in spec["preferred"]


def test_build_wechat_feed_match_spec_with_main_line2():
    spec = build_wechat_feed_match_spec(
        None,
        "英伟达前AI总监推5万亿上下文",
        main_line1="英伟达前AI总监推5万亿上下文",
        main_line2="网友：5万亿上下文？先别吹",
        sub_title="5万亿上下文，一次推演整个时空",
    )
    assert spec["required"] == ["5万亿上下文，一次推演整个时空"]
    assert "网友：5万亿上下文？先别吹" in spec["preferred"] or "英伟达前AI总监推5万亿上下文" in spec["preferred"]


def test_extract_wechat_copy_lines_uses_description_order():
    description = (
        "522万分，国产芯片的分水岭\n"
        "跑分破500万，实际体验能打吗？\n"
        "小牛说：小米玄戒O3发布"
    )
    copy = extract_wechat_copy_lines(
        description,
        main_line1="小米玄戒O3安兔兔跑分破500万",
        sub_title="522万分，国产芯片的分水岭",
    )
    assert copy["main_line1"] == "小米玄戒O3安兔兔跑分破500万"
    assert copy["sub_title"] == "522万分，国产芯片的分水岭"
    assert copy["sub_title2"] == "跑分破500万，实际体验能打吗？"


def test_build_wechat_comment_hub_needles_from_description():
    description = (
        "小牛说：前台也能谈大生意\n"
        "网友：没投钱拿近300亿？ 外看高"
    )
    needles = build_wechat_comment_hub_needles(
        description,
        "英伟达前台",
        main_line2="网友：没投钱拿近300亿？ 外看高",
    )
    assert needles[0] == "网友：没投钱拿近300亿？ 外看高"


def test_post_id_from_row_platforms():
    assert post_id_from_row("wechat_channels", {"export_id": "export/x"}) == "export/x"
    assert post_id_from_row("kuaishou", {"photo_id": "photo123"}) == "photo123"
    assert post_id_from_row("kuaishou", {"work_id": "work456"}) == "work456"
    assert post_id_from_row("douyin", {"video_id": "7673873560674290944"}) == "7673873560674290944"


def test_parse_douyin_comment_list_payload():
    payload = {
        "status_code": 0,
        "comments": [
            {
                "cid": "7681412220375466789",
                "text": "观众评论内容足够长",
                "create_time": 1788468162,
                "user": {"nickname": "路人甲"},
                "reply_comment": None,
            }
        ],
        "has_more": 0,
        "cursor": 10,
    }
    rows = parse_douyin_comment_list_payload(
        payload,
        video_id="7673873560674290944",
        post_title="测试标题",
        account_nickname="小牛聊AI",
    )
    assert len(rows) == 1
    assert rows[0].platform_comment_id == "7681412220375466789"
    assert rows[0].content == "观众评论内容足够长"
    assert rows[0].author_name == "路人甲"


def test_parse_douyin_comment_list_payload_detects_inline_reply_comment():
    payload = {
        "status_code": 0,
        "comments": [
            {
                "cid": "c1",
                "text": "观众评论",
                "user": {"nickname": "路人"},
                "reply_comment": {"user": {"nickname": "小牛聊AI"}, "text": "谢谢支持"},
            }
        ],
    }
    rows = parse_douyin_comment_list_payload(
        payload,
        video_id="vid1",
        post_title=None,
        account_nickname="小牛聊AI",
    )
    assert rows[0].already_replied_by_author is True


def test_author_replied_in_douyin_reply_payload():
    payload = {
        "status_code": 0,
        "comments": [
            {"user": {"nickname": "路人乙"}},
            {"user": {"nickname": "小牛聊AI"}},
        ],
    }
    assert _author_replied_in_douyin_reply_payload(payload, "小牛聊AI") is True
    assert _author_replied_in_douyin_reply_payload(payload, "其他账号") is False


def test_author_replied_in_douyin_item_collapsed_thread():
    item = {"reply_comment": None, "reply_comment_total": 3}
    assert _author_replied_in_douyin_item(item, "小牛聊AI") is False


def test_douyin_author_already_replied_in_thread_fetches_reply_list():
    page = MagicMock()
    page.evaluate.side_effect = [
        {
            "status_code": 0,
            "comments": [{"user": {"nickname": "小牛聊AI"}, "text": "已回复"}],
            "has_more": 0,
        }
    ]
    raw_item = {"reply_comment": None, "reply_comment_total": 2}
    assert douyin_author_already_replied_in_thread(
        page,
        video_id="vid1",
        comment_id="c1",
        account_nickname="小牛聊AI",
        raw_item=raw_item,
    ) is True
    page.evaluate.assert_called_once()


def test_apply_douyin_reply_state_marks_collapsed_thread():
    page = MagicMock()
    page.evaluate.return_value = {
        "status_code": 0,
        "comments": [{"user": {"nickname": "小牛聊AI"}}],
        "has_more": 0,
    }
    comment = InboundComment(
        platform_post_id="vid1",
        platform_comment_id="c1",
        author_name="路人",
        content="评论内容",
        commented_at=None,
        already_replied_by_author=False,
    )
    enriched = _apply_douyin_reply_state(
        page,
        video_id="vid1",
        comment=comment,
        raw_item={"reply_comment": None, "reply_comment_total": 1},
        account_nickname="小牛聊AI",
    )
    assert enriched.already_replied_by_author is True


def test_author_replied_in_douyin_reply_payload_matches_reply_text():
    payload = {
        "status_code": 0,
        "comments": [
            {"user": {"nickname": "路人甲"}, "text": "这个观点很有意思，值得再聊聊"},
        ],
    }
    assert _author_replied_in_douyin_reply_payload(
        payload,
        "未来读书人",
        expected_reply_text="这个观点很有意思，值得再聊聊",
    ) is True
    assert _author_replied_in_douyin_reply_payload(payload, "未来读书人") is False


def test_nickname_matches_partial_suffix():
    from services.publishing.adapters.douyin_audience_reply import _nickname_matches

    assert _nickname_matches("未来读书人", "未来读书人·官方") is True
    assert _nickname_matches("未来读书人", "其他账号") is False


def test_author_replied_in_douyin_item_matches_reply_text():
    item = {
        "reply_comment": {
            "text": "感谢支持，我们会继续分享好书",
            "user": {"nickname": "某个昵称"},
        }
    }
    assert _author_replied_in_douyin_item(
        item,
        "未来读书人",
        expected_reply_text="感谢支持，我们会继续分享好书",
    ) is True


def test_resolve_douyin_submit_result_matches_cached_reply_text():
    page = MagicMock()
    page.evaluate.return_value = {
        "status_code": 0,
        "comments": [
            {"user": {"nickname": "路人"}, "text": "感谢你的留言，一起读书"},
        ],
        "has_more": 0,
    }
    comment = InboundComment(
        platform_post_id="vid1",
        platform_comment_id="c1",
        author_name="路人",
        content="评论内容",
        commented_at=None,
    )
    from services.publishing.adapters.douyin_audience_reply import _resolve_douyin_submit_result

    result = _resolve_douyin_submit_result(
        page,
        video_id="vid1",
        comment=comment,
        account_nickname="未来读书人",
        verified=False,
        error_message="submit_not_confirmed",
        reply_text="感谢你的留言，一起读书",
    )
    assert result.success is True


def test_resolve_douyin_submit_result_when_reply_visible_despite_verify_fail():
    page = MagicMock()
    page.evaluate.return_value = {
        "status_code": 0,
        "comments": [{"user": {"nickname": "小牛聊AI"}}],
        "has_more": 0,
    }
    comment = InboundComment(
        platform_post_id="vid1",
        platform_comment_id="c1",
        author_name="路人",
        content="评论内容",
        commented_at=None,
    )
    from services.publishing.adapters.douyin_audience_reply import _resolve_douyin_submit_result

    result = _resolve_douyin_submit_result(
        page,
        video_id="vid1",
        comment=comment,
        account_nickname="小牛聊AI",
        verified=False,
        error_message="submit_not_confirmed",
    )
    assert result.success is True
    assert result.comment_id == "c1"


def test_reply_douyin_skips_when_collapsed_thread_already_replied():
    page = MagicMock()
    page.evaluate.return_value = {
        "status_code": 0,
        "comments": [{"user": {"nickname": "小牛聊AI"}}],
        "has_more": 0,
    }
    session = PostCommentSession(
        platform_post_id="vid1",
        post_title="标题",
        hub_feed_text=None,
        feed_match_spec=None,
        feed_active=True,
        post_context_json=None,
    )
    comment = InboundComment(
        platform_post_id="vid1",
        platform_comment_id="c1",
        author_name="路人",
        content="评论内容",
        commented_at=None,
        already_replied_by_author=False,
    )
    result = reply_douyin_audience_comment_on_active_feed(
        page,
        session=session,
        comment=comment,
        reply_text="感谢留言",
        account_nickname="小牛聊AI",
    )
    assert result.success is False
    assert result.error_message == "already_replied"


def test_parse_wechat_comment_list_payload():
    payload = {
        "errCode": 0,
        "data": {
            "comment": [
                {
                    "commentId": "123",
                    "commentNickname": "观众A",
                    "commentContent": "这个靠谱吗？",
                    "commentCreatetime": "1788074313",
                    "levelTwoComment": [],
                }
            ]
        },
    }
    rows = parse_wechat_comment_list_payload(
        payload,
        export_id="export/test",
        post_title="测试标题",
        account_nickname="小牛聊AI",
    )
    assert len(rows) == 1
    assert rows[0].platform_comment_id == "123"
    assert rows[0].content == "这个靠谱吗？"


def test_parse_kuaishou_comment_list_payload():
    payload = {
        "result": 1,
        "data": {
            "list": [
                {
                    "commentId": "ks-1",
                    "userName": "路人甲",
                    "content": "讲得很清楚",
                    "timestamp": 1788074313000,
                    "replyList": [],
                }
            ]
        },
    }
    rows = parse_kuaishou_comment_list_payload(
        payload,
        photo_id="photo-1",
        post_title="测试",
        account_nickname="小牛",
    )
    assert len(rows) == 1
    assert rows[0].platform_comment_id == "ks-1"
    assert rows[0].author_name == "路人甲"


def test_should_skip_author_own_comment():
    comment = InboundComment(
        platform_post_id="export/x",
        platform_comment_id="1",
        author_name="小牛聊AI",
        content="你觉得呢？",
        commented_at=datetime.utcnow(),
    )
    assert should_skip_comment(comment, account_nickname="小牛聊AI", author_first_comments=set()) == "author_own_comment"


def test_should_skip_when_author_already_replied():
    comment = InboundComment(
        platform_post_id="export/x",
        platform_comment_id="1",
        author_name="路人",
        content="说得对",
        commented_at=datetime.utcnow(),
        already_replied_by_author=True,
    )
    assert should_skip_comment(comment, account_nickname="小牛聊AI", author_first_comments=set()) == "already_replied"


def test_validate_reply_text_length():
    assert validate_reply_text("这是一句足够长的回复", min_length=5, max_length=100) == "这是一句足够长的回复"


def test_save_comment_reply_settings_lookback_hours(tmp_path, monkeypatch):
    local_path = tmp_path / "config" / "publishing_platforms.local.yaml"
    monkeypatch.setattr(
        "services.publishing.comment_reply.settings.PUBLISHING_LOCAL_PATH",
        local_path,
    )
    monkeypatch.setattr(
        "services.publishing.comment_reply.config.PUBLISHING_LOCAL_PATH",
        local_path,
    )
    from services.publishing.comment_reply.settings import (
        get_comment_reply_settings,
        save_comment_reply_settings,
    )

    save_comment_reply_settings(lookback_hours=72)
    assert get_comment_reply_settings()["lookback_hours"] == 72


def test_save_comment_reply_settings_rejects_invalid_lookback(tmp_path, monkeypatch):
    local_path = tmp_path / "config" / "publishing_platforms.local.yaml"
    monkeypatch.setattr(
        "services.publishing.comment_reply.settings.PUBLISHING_LOCAL_PATH",
        local_path,
    )
    monkeypatch.setattr(
        "services.publishing.comment_reply.config.PUBLISHING_LOCAL_PATH",
        local_path,
    )
    import pytest

    from services.publishing.comment_reply.settings import save_comment_reply_settings

    with pytest.raises(ValueError, match="lookback_hours"):
        save_comment_reply_settings(lookback_hours=0)
