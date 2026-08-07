from services.publishing.adapters.xiaohongshu_form import (
    compose_xiaohongshu_description,
    format_xiaohongshu_tags,
    normalize_xiaohongshu_title,
)


def test_normalize_xiaohongshu_title_truncates():
    long_title = "A" * 30
    assert len(normalize_xiaohongshu_title(long_title, max_length=20)) == 20


def test_format_xiaohongshu_tags():
    assert format_xiaohongshu_tags(["AI", "#科技"]) == "#AI #科技"


def test_douyin_video_ready_texts_defined():
    from services.publishing.adapters.douyin_form import VIDEO_READY_TEXTS

    assert "设置封面" in VIDEO_READY_TEXTS


def test_xhs_publish_selectors_include_web_component():
    from services.publishing.adapters.xiaohongshu_form import XHS_PUBLISH_BUTTON_SELECTORS

    assert "xhs-publish-btn" in XHS_PUBLISH_BUTTON_SELECTORS
    text = compose_xiaohongshu_description("正文", ["AI"])
    assert text == "正文\n#AI"
