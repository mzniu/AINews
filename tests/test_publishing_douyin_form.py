from unittest.mock import MagicMock, patch

from services.publishing.adapters.douyin_form import (
    DOUYIN_AI_COVER_WAIT_MAX_MS,
    DOUYIN_COVER_SELECT_MAX_MS,
    RECOMMEND_COVER_CONTAINER_SELECTOR,
    RECOMMEND_COVER_ITEM_SELECTOR,
    TITLE_SELECTORS,
    UPLOADING_PATTERN,
    VIDEO_READY_TEXTS,
    ai_cover_probe_is_ready,
    format_douyin_tags,
    normalize_douyin_title,
)
from services.publishing.human_interaction import human_type_text


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


def test_cover_select_timeout_allows_ai_generation():
    assert DOUYIN_COVER_SELECT_MAX_MS >= 30_000
    assert DOUYIN_AI_COVER_WAIT_MAX_MS >= 60_000


def test_ai_cover_probe_requires_ai_marker():
    assert not ai_cover_probe_is_ready(None)
    assert not ai_cover_probe_is_ready({"count": 2, "hasAi": False, "checking": False})
    assert not ai_cover_probe_is_ready({"count": 1, "hasAi": True, "checking": True})
    assert ai_cover_probe_is_ready({"count": 1, "hasAi": True, "checking": False})


def test_ai_cover_probe_can_relax_require_ai():
    assert ai_cover_probe_is_ready({"count": 2, "hasAi": False, "checking": False}, require_ai=False)


def test_douyin_title_selectors_avoid_generic_contenteditable():
    assert '[contenteditable="true"]' not in TITLE_SELECTORS


DOUYIN_AI_DECLARATION_HTML = """
<!DOCTYPE html>
<html><body>
  <button id="open">自主声明</button>
  <div id="panel" hidden>
    <label><input type="checkbox" id="ai">内容由AI生成</label>
    <button id="ok">确定</button>
  </div>
  <script>
    document.getElementById('open').addEventListener('click', () => {
      document.getElementById('panel').hidden = false;
    });
    document.getElementById('ok').addEventListener('click', () => {
      window.__aiDeclared = document.getElementById('ai').checked;
    });
  </script>
</body></html>
"""


def test_declare_douyin_ai_generated_clicks_option():
    from playwright.sync_api import sync_playwright

    from services.publishing.adapters.douyin_form import declare_douyin_ai_generated

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(DOUYIN_AI_DECLARATION_HTML)
            asserted = declare_douyin_ai_generated(page)
            declared = page.evaluate("() => window.__aiDeclared === true")
        finally:
            browser.close()

    assert asserted is True
    assert declared is True


def test_declare_douyin_ai_generated_missing_control_is_false():
    from playwright.sync_api import sync_playwright

    from services.publishing.adapters.douyin_form import declare_douyin_ai_generated

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content("<html><body><button>发布</button></body></html>")
            asserted = declare_douyin_ai_generated(page)
        finally:
            browser.close()

    assert asserted is False


@patch("services.publishing.human_interaction.human_click")
@patch("services.publishing.human_interaction.human_pause")
def test_human_type_text_clears_inside_locator_not_page(mock_pause, mock_click):
    page = MagicMock()
    locator = MagicMock()
    human_type_text(page, locator, "标题", clear_first=True)
    locator.evaluate.assert_called_once()
    clear_script = locator.evaluate.call_args[0][0]
    assert "el.select()" in clear_script
    assert "Control+a" not in clear_script
    page.keyboard.press.assert_called_with("Backspace")
