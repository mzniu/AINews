from services.publishing.adapters.publish_button_helpers import (
    DEFAULT_PUBLISH_TEXTS,
    DEFAULT_SUCCESS_PATTERN,
    url_suggests_publish_success,
)


def test_default_publish_texts_include_common_labels():
    assert "发布" in DEFAULT_PUBLISH_TEXTS
    assert "发表" in DEFAULT_PUBLISH_TEXTS


def test_default_success_pattern_matches_publish_success():
    assert DEFAULT_SUCCESS_PATTERN.search("发布成功")
    assert DEFAULT_SUCCESS_PATTERN.search("发表成功")
    assert DEFAULT_SUCCESS_PATTERN.search("发表完成")


def test_url_suggests_publish_success_for_wechat_post_list():
    initial = "https://channels.weixin.qq.com/platform/post/create"
    current = "https://channels.weixin.qq.com/platform/post/list"
    assert url_suggests_publish_success(initial, current)


def test_url_suggests_publish_success_ignores_same_page():
    url = "https://channels.weixin.qq.com/platform/post/create"
    assert not url_suggests_publish_success(url, url)
