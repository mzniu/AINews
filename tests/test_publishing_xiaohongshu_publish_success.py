from services.publishing.adapters.xiaohongshu_form import (
    XHS_PUBLISH_FAILURE_PATTERN,
    XHS_PUBLISH_SUCCESS_PATTERN,
    _publish_label_matches,
    xhs_url_suggests_publish_success,
)


def test_publish_label_matches_variants():
    assert _publish_label_matches("发布")
    assert _publish_label_matches("发布笔记")
    assert _publish_label_matches("")
    assert not _publish_label_matches("保存草稿")


def test_xhs_success_pattern_does_not_match_sidebar_only():
    assert not XHS_PUBLISH_SUCCESS_PATTERN.search("笔记管理")
    assert XHS_PUBLISH_SUCCESS_PATTERN.search("发布成功，前往笔记管理查看")


def test_xhs_failure_pattern_matches_validation_errors():
    assert XHS_PUBLISH_FAILURE_PATTERN.search("请填写标题")
    assert XHS_PUBLISH_FAILURE_PATTERN.search("发布失败，请稍后重试")


def test_xhs_url_suggests_publish_success():
    initial = "https://creator.xiaohongshu.com/publish/publish?source=official"
    success = "https://creator.xiaohongshu.com/publish/success?noteId=abc"
    home = "https://creator.xiaohongshu.com/new/home"
    assert xhs_url_suggests_publish_success(initial, success)
    assert xhs_url_suggests_publish_success(initial, home)
    assert not xhs_url_suggests_publish_success(initial, initial)
