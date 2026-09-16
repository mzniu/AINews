"""Tests for comment reply post context snapshots."""
from services.publishing.adapters.wechat_channels_audience_reply import build_wechat_feed_match_spec
from services.publishing.comment_reply.post_context import (
    build_wechat_inbox_post_context,
    match_spec_from_post_context,
    parse_post_context,
)


def test_build_wechat_inbox_post_context_prefers_hub_feed_text():
    ctx = build_wechat_inbox_post_context(
        post_row={
            "export_id": "export/abc",
            "title": "短标题",
            "hub_feed_text": "英伟达前AI总监推5万亿上下文 网友：5万亿上下文？先别吹 5万亿上下文，是实测还是概念？",
        },
        job=None,
        session=None,  # type: ignore[arg-type]
    )
    assert ctx["hub_feed_text"].startswith("英伟达前AI总监")
    assert ctx["feed_match_required"] == [ctx["hub_feed_text"][:160]]


def test_match_spec_from_post_context():
    ctx = parse_post_context(
        '{"feed_match_required":["英伟达前AI总监推5万亿上下文 网友：5万亿上下文？先别吹"],"hub_feed_text":"英伟达前AI总监推5万亿上下文 网友：5万亿上下文？先别吹"}'
    )
    spec = match_spec_from_post_context(ctx)
    assert spec is not None
    assert spec["required"][0].startswith("英伟达前AI总监")


def test_match_spec_rebuilds_old_dual_required():
    ctx = parse_post_context(
        '{"feed_match_required":["小米玄戒O3 安兔兔跑分破500万","522万分，国产芯片的分水岭"],'
        '"main_line1":"小米玄戒O3 安兔兔跑分破500万","sub_title":"522万分，国产芯片的分水岭"}'
    )
    spec = match_spec_from_post_context(ctx)
    assert spec is not None
    assert spec["required"] == ["522万分，国产芯片的分水岭"]


def test_match_spec_rebuilds_stale_main_line1_required():
    ctx = parse_post_context(
        '{"feed_match_required":["众擎CEO闭关研发大脑"],'
        '"main_line1":"众擎CEO闭关研发大脑",'
        '"description":"本体决定上桌，大脑决定留多久\\n网友：大脑缺高手，补四个月够吗"}'
    )
    spec = match_spec_from_post_context(ctx)
    assert spec is not None
    assert spec["required"] == ["本体决定上桌，大脑决定留多久"]


def test_build_wechat_feed_match_spec_from_description_only_main_line1():
    description = (
        "本体决定上桌，大脑决定留多久\n"
        "网友：大脑缺高手，补四个月够吗\n"
        "60%投大脑，真能补到80分？\n"
        "小牛说：宇树敲钟当天，众擎却闭关补脑"
    )
    spec = build_wechat_feed_match_spec(
        description,
        "众擎CEO闭关研发大脑",
        main_line1="众擎CEO闭关研发大脑",
    )
    assert spec["required"] == ["本体决定上桌，大脑决定留多久"]
    sidebar = (
        "本体决定上桌，大脑决定留多久 网友：大脑缺高手，补四个月够吗 "
        "60%投大脑，真能补到80分？ 小牛说：宇树敲钟当天，众擎却闭关补脑"
    )
    from services.publishing.adapters.wechat_channels_audience_reply import sidebar_text_matches_spec

    assert sidebar_text_matches_spec(sidebar, spec)
    assert not sidebar_text_matches_spec(sidebar, {"required": ["众擎CEO闭关研发大脑"], "preferred": []})
