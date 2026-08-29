from unittest.mock import MagicMock

from playwright.sync_api import sync_playwright
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
        "轻观点收尾",
        "网友：厉害了",
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


def test_compose_post_desc_text_keeps_hashtags_in_description():
    text = compose_post_desc_text(
        description=(
            "网友：27B能跑，别吹超Opus\n"
            "小牛说：阿里开源270亿参数多模态模型。\n"
            "#AI开源 #多模态模型 #Qwen3 #小牛说 #懂开源"
        ),
        tags=["懂开源含金量"],
    )
    assert text == (
        "网友：27B能跑，别吹超Opus\n"
        "小牛说：阿里开源270亿参数多模态模型。\n"
        "#AI开源 #多模态模型 #Qwen3 #小牛说 #懂开源"
    )


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


WUJIE_SHADOW_FORM_HTML = """
<!DOCTYPE html>
<html><body>
  <div>外壳页面，不含标题输入框</div>
  <wujie-app></wujie-app>
  <script>
    const host = document.querySelector('wujie-app');
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `
      <textarea placeholder="填写标题"></textarea>
      <div class="post-desc-box">
        <div class="input-editor" data-placeholder="添加描述" contenteditable="true"></div>
      </div>
      <span>声明原创</span>
      <button>发表</button>
    `;
  </script>
</body></html>
"""


def test_probe_sees_form_inside_wujie_shadow_dom():
    from services.publishing.adapters.wechat_channels_form import _probe_wechat_upload_state

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(WUJIE_SHADOW_FORM_HTML)
            state = _probe_wechat_upload_state(page)
        finally:
            browser.close()

    assert state.get("hasTitle") is True
    assert state.get("hasDescEditor") is True
    assert state.get("editorReady") is True
    assert state.get("publishEnabled") is True
    assert state.get("stillUploading") is False


BOUND_EDITOR_HTML = """
<!DOCTYPE html>
<html><body>
  <wujie-app></wujie-app>
  <script>
    const host = document.querySelector('wujie-app');
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `
      <textarea placeholder="填写标题"></textarea>
      <div class="post-desc-box">
        <div class="input-editor" data-placeholder="添加描述" contenteditable="true"></div>
      </div>
      <button>发表</button>
    `;
    const el = shadow.querySelector('.input-editor');
    window.__publishDesc = '';
    el.addEventListener('beforeinput', (e) => {
      if (e.inputType === 'insertText' && e.data) {
        window.__publishDesc += e.data;
      } else if (e.inputType === 'insertParagraph' || e.inputType === 'insertLineBreak') {
        window.__publishDesc += '\\n';
      }
    });
  </script>
</body></html>
"""


def test_fill_wechat_description_updates_editor_document():
    from services.publishing.adapters.wechat_channels_form import fill_wechat_description

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(BOUND_EDITOR_HTML)
            ok = fill_wechat_description(page, "小牛说测试摘要", timeout_ms=8000)
            bound = page.evaluate("() => window.__publishDesc")
        finally:
            browser.close()

    assert ok is True
    assert "小牛说测试摘要" in str(bound).replace("\n", "")


def test_ensure_wechat_description_refills_after_editor_wipe():
    from services.publishing.adapters.wechat_channels_form import (
        ensure_wechat_description,
        fill_wechat_description,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(BOUND_EDITOR_HTML)
            assert fill_wechat_description(page, "小牛说测试摘要", timeout_ms=8000) is True
            page.evaluate(
                """() => {
                    const el = document.querySelector('wujie-app').shadowRoot.querySelector('.input-editor');
                    el.innerHTML = '';
                    window.__publishDesc = '';
                }"""
            )
            ok = ensure_wechat_description(page, "小牛说测试摘要", timeout_ms=8000)
            bound = page.evaluate("() => window.__publishDesc")
        finally:
            browser.close()

    assert ok is True
    assert "小牛说测试摘要" in str(bound).replace("\n", "")


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
