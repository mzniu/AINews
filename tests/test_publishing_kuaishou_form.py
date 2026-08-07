from services.publishing.adapters.kuaishou_form import (
    DESCRIPTION_SELECTORS,
    GUIDE_TOOLTIP_SKIP_SELECTORS,
    UPLOAD_ADVANCE_TEXTS,
    UPLOAD_TRIGGER_TEXTS,
    compose_kuaishou_description,
    format_kuaishou_tags,
    normalize_kuaishou_title,
    normalize_kuaishou_tags,
)


def test_normalize_kuaishou_title_truncates():
    long_title = "A" * 60
    assert len(normalize_kuaishou_title(long_title, max_length=50)) == 50


def test_format_kuaishou_tags():
    assert format_kuaishou_tags(["AI", "#资讯"]) == "#AI #资讯"


def test_compose_kuaishou_description_with_tags():
    text = compose_kuaishou_description("正文", ["AI"])
    assert text == "正文\n#AI"


def test_compose_kuaishou_description_dedupes_embedded_tags():
    text = compose_kuaishou_description("正文\n#AI #科技", ["AI", "资讯"])
    assert text == "正文\n#AI #科技 #资讯"


def test_compose_kuaishou_description_limits_tags_to_four():
    text = compose_kuaishou_description("正文", ["一", "二", "三", "四", "五"], max_tags=4)
    assert text == "正文\n#一 #二 #三 #四"


def test_description_selectors_prioritize_work_description_edit():
    assert DESCRIPTION_SELECTORS[0] == "#work-description-edit"


def test_upload_triggers_avoid_generic_upload_text():
    assert "上传" not in UPLOAD_TRIGGER_TEXTS
    assert "上传视频" in UPLOAD_TRIGGER_TEXTS


def test_upload_advance_texts_include_next_step():
    assert "下一步" in UPLOAD_ADVANCE_TEXTS


def test_guide_tooltip_skip_selectors_target_skip_action():
    assert any("skip" in selector for selector in GUIDE_TOOLTIP_SKIP_SELECTORS)


def test_normalize_kuaishou_tags_dedupes_and_limits():
    assert normalize_kuaishou_tags(["AI", "#AI", "科技", "资讯", "热点"], max_tags=4) == [
        "AI",
        "科技",
        "资讯",
        "热点",
    ]
