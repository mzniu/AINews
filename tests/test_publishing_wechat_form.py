from unittest.mock import MagicMock

from services.publishing.adapters.wechat_channels_form import (
    WECHAT_UPLOADING_PATTERN,
    WECHAT_UPLOAD_REQUIRED_PATTERN,
    WECHAT_VIDEO_READY_MAX_MS,
    _ant_checkbox_checked,
    compose_post_desc_text,
)


def test_compose_post_desc_text_from_structured_fields():
    text = compose_post_desc_text(
        main_line2="网友：厉害了",
        sub_title="轻观点收尾",
        sub_title2="钩子句",
        summary="小牛说：这是摘要",
        tags=["AI", "大模型"],
    )
    lines = text.splitlines()
    assert lines == [
        "网友：厉害了",
        "轻观点收尾",
        "钩子句",
        "小牛说：这是摘要",
        "#AI #大模型",
    ]


def test_compose_post_desc_text_prefers_description():
    text = compose_post_desc_text(
        description="已有描述\n第二行",
        main_line2="应忽略",
    )
    assert text == "已有描述\n第二行"


def test_ant_checkbox_checked_reads_class():
    label = MagicMock()
    checkbox = MagicMock()
    checkbox.get_attribute.return_value = "ant-checkbox ant-checkbox-checked"
    input_el = MagicMock()
    input_el.is_checked.side_effect = Exception("skip")

    def locator_side_effect(selector: str):
        child = MagicMock()
        child.first = checkbox if "span.ant-checkbox" in selector else input_el
        return child

    label.locator.side_effect = locator_side_effect
    assert _ant_checkbox_checked(label) is True


def test_ant_checkbox_checked_reads_input():
    label = MagicMock()
    checkbox = MagicMock()
    checkbox.get_attribute.return_value = "ant-checkbox"
    input_el = MagicMock()
    input_el.is_checked.return_value = True

    def locator_side_effect(selector: str):
        child = MagicMock()
        child.first = checkbox if "span.ant-checkbox" in selector else input_el
        return child

    label.locator.side_effect = locator_side_effect
    assert _ant_checkbox_checked(label) is True


def test_wechat_upload_required_pattern_matches_prompt():
    assert WECHAT_UPLOAD_REQUIRED_PATTERN.search("请上传视频")


def test_wechat_uploading_pattern_matches_progress():
    assert WECHAT_UPLOADING_PATTERN.search("上传中 45%")


def test_wechat_video_ready_timeout_is_reasonable():
    assert WECHAT_VIDEO_READY_MAX_MS >= 60_000


def test_is_video_file_input_rejects_image_only():
    from unittest.mock import MagicMock

    from services.publishing.adapters.wechat_channels_form import _is_video_file_input

    image_only = MagicMock()
    image_only.get_attribute.return_value = "image/jpeg,image/png"
    assert _is_video_file_input(image_only) is False

    video = MagicMock()
    video.get_attribute.return_value = "video/mp4"
    assert _is_video_file_input(video) is True

    empty = MagicMock()
    empty.get_attribute.return_value = ""
    assert _is_video_file_input(empty) is True
