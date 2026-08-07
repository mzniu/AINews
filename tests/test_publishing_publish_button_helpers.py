from services.publishing.adapters.publish_button_helpers import (
    DEFAULT_PUBLISH_TEXTS,
    DEFAULT_SUCCESS_PATTERN,
)


def test_default_publish_texts_include_common_labels():
    assert "发布" in DEFAULT_PUBLISH_TEXTS
    assert "发表" in DEFAULT_PUBLISH_TEXTS


def test_default_success_pattern_matches_publish_success():
    assert DEFAULT_SUCCESS_PATTERN.search("发布成功")
    assert DEFAULT_SUCCESS_PATTERN.search("发表成功")
