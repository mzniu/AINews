from services.publishing.metadata_bridge import (
    PublishDraftMetadata,
    draft_from_video_draft,
    draft_to_publish_fields,
    normalize_wechat_title,
)


def test_draft_maps_title_description_tags():
    draft = PublishDraftMetadata(
        main_line1="突发！",
        main_line2="网友：厉害了",
        sub_title="轻观点收尾",
        sub_title2="钩子句",
        summary="小牛说：这是摘要",
        short_title="DeepSeek发布",
        praise_tags=["AI", "大模型"],
    )
    out = draft_to_publish_fields(draft, max_title_length=30, max_tags=10)
    assert out["title"] == "DeepSeek发布"
    assert "网友：厉害了" in out["description"]
    assert "轻观点收尾" in out["description"]
    assert "钩子句" in out["description"]
    assert "小牛说：这是摘要" in out["description"]
    assert "#AI" in out["description"] or "AI" in out["description"]
    assert out["tags"] == ["AI", "大模型"]


def test_wechat_title_falls_back_to_main_line1():
    draft = PublishDraftMetadata(main_line1="成片主标题可以更长一些", short_title="")
    out = draft_to_publish_fields(draft, platform_id="wechat_channels")
    assert out["title"] == "成片主标题可以更长一些"


def test_other_platforms_keep_main_line1():
    draft = PublishDraftMetadata(
        main_line1="成片主标题可以更长一些",
        short_title="视频号短标题",
    )
    out = draft_to_publish_fields(draft, platform_id="douyin", max_title_length=30)
    assert out["title"] == "成片主标题可以更长一些"


def test_normalize_wechat_title_strips_all_punctuation():
    assert normalize_wechat_title("炸裂！突发！") == "炸裂突发"
    assert normalize_wechat_title("GPT-4.5 来了！") == "GPT4点5 来了"


def test_wechat_title_caps_at_16_including_spaces():
    draft = PublishDraftMetadata(short_title=("甲" * 8) + " " + ("乙" * 8))
    out = draft_to_publish_fields(draft, platform_id="wechat_channels")
    assert out["title"] == ("甲" * 8) + " " + ("乙" * 7)
    assert len(out["title"]) == 16


def test_draft_from_video_draft_with_tags_string():
    draft = draft_from_video_draft(
        {
            "main_line1": "突发！",
            "main_line2": "第二行",
            "sub_title": "副标题",
            "summary": "摘要内容",
            "tags": "#AI #小牛说",
        }
    )
    out = draft_to_publish_fields(draft)
    assert out["title"] == "突发"
    assert out["description"].splitlines() == [
        "副标题",
        "第二行",
        "摘要内容",
        "#AI #小牛说",
    ]
