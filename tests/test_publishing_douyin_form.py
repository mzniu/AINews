from services.publishing.adapters.douyin_form import (
    DOUYIN_COVER_SELECT_MAX_MS,
    RECOMMEND_COVER_CONTAINER_SELECTOR,
    RECOMMEND_COVER_ITEM_SELECTOR,
    UPLOADING_PATTERN,
    VIDEO_READY_TEXTS,
    format_douyin_tags,
    normalize_douyin_title,
)


def test_normalize_douyin_title_truncates():
    long_title = "A" * 60
    assert len(normalize_douyin_title(long_title, max_length=55)) == 55


def test_normalize_douyin_title_replaces_exclamation():
    assert normalize_douyin_title("你好！") == "你好？"


def test_douyin_video_ready_texts_defined():
    assert "设置封面" in VIDEO_READY_TEXTS


def test_douyin_recommend_cover_selectors():
    assert "recommendCoverContainer" in RECOMMEND_COVER_CONTAINER_SELECTOR
    assert "recommendCoverContainer" in RECOMMEND_COVER_ITEM_SELECTOR
    assert "recommendCover" in RECOMMEND_COVER_ITEM_SELECTOR


def test_format_douyin_tags():
    assert format_douyin_tags(["AI", "#资讯"]) == "#AI #资讯"


def test_uploading_pattern_ignores_generic_processing_text():
    assert not UPLOADING_PATTERN.search("数据处理中心")
    assert UPLOADING_PATTERN.search("正在上传 45%")


def test_cover_select_timeout_is_short():
    assert DOUYIN_COVER_SELECT_MAX_MS <= 10_000
