"""Helpers for filling WeChat Channels publish form fields."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from services.publishing.human_form import (
    human_click_element,
    human_fill,
    human_upload_file,
)
from services.publishing.human_interaction import human_type_text
from services.publishing.human_pacing import human_pause

from services.publishing.metadata_bridge import PublishDraftMetadata, build_wechat_description, normalize_wechat_title

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

TITLE_SELECTORS = (
    'wujie-app >> textarea[placeholder*="标题"]',
    'wujie-app >> input[placeholder*="标题"]',
    'textarea[placeholder*="标题"]',
    'input[placeholder*="标题"]',
)

POST_DESC_EDITOR_SELECTORS = (
    'wujie-app >> .post-desc-box div.input-editor[data-placeholder="添加描述"]',
    '.post-desc-box div.input-editor[data-placeholder="添加描述"]',
    'div.post-desc-box .input-editor[contenteditable]',
    'div.input-editor[data-placeholder="添加描述"]',
)

DESCRIPTION_SELECTORS = POST_DESC_EDITOR_SELECTORS + (
    'wujie-app >> [contenteditable="true"]',
    'wujie-app >> textarea[placeholder*="描述"]',
    'wujie-app >> textarea[placeholder*="简介"]',
    '[contenteditable="true"]',
    'textarea[placeholder*="描述"]',
    'textarea[placeholder*="简介"]',
    'textarea[placeholder*="说点什么"]',
)

DESCRIPTION_PLACEHOLDERS = (
    "添加描述",
    "说点什么",
    "视频描述",
    "作品描述",
    "简介",
    "描述",
)

_TOPIC_HINTS = ("话题", "tag", "#", "搜索")

COVER_TRIGGER_TEXTS = ("更换封面", "编辑封面", "修改封面", "选择封面", "上传封面", "设置封面")

COVER_FILE_SELECTORS = (
    'wujie-app >> input[type="file"][accept*="image"]',
    'input[type="file"][accept*="image"]',
    'input[type="file"][accept*=".jpg"]',
    'input[type="file"][accept*=".jpeg"]',
    'input[type="file"][accept*=".png"]',
)

DECLARE_ORIGINAL_SECTION_SELECTORS = (
    'wujie-app >> .declare-original-checkbox',
    '.declare-original-checkbox',
)

ORIGINAL_DIALOG_TITLE = "原创权益"

UPLOAD_TRIGGER_TEXTS = ("上传视频", "点击上传", "上传", "发视频", "发表视频")

WECHAT_VIDEO_FILE_SELECTORS = (
    'wujie-app >> input[type="file"][accept*="video"]',
    'wujie-app >> input[type="file"][accept*="mp4"]',
    'input[type="file"][accept*="video"]',
    'input[type="file"][accept*="mp4"]',
    'wujie-app >> input[type="file"]',
    'input[type="file"]',
)

WECHAT_UPLOADING_PATTERN = re.compile(r"上传中|正在上传|解析中|转码|处理中", re.I)
WECHAT_UPLOAD_REQUIRED_PATTERN = re.compile(r"请上传视频")
WECHAT_VIDEO_READY_MARKERS = ("添加描述", "声明原创", "更换封面", "编辑封面", "设置封面")
WECHAT_VIDEO_READY_MAX_MS = 180_000


def compose_post_desc_text(
    *,
    main_line2: str = "",
    sub_title: str = "",
    sub_title2: str = "",
    summary: str = "",
    tags: list[str] | None = None,
    description: str | None = None,
) -> str:
    if description and description.strip():
        return description.strip()
    draft = PublishDraftMetadata(
        main_line2=main_line2,
        sub_title=sub_title,
        sub_title2=sub_title2,
        summary=summary,
        praise_tags=[],
        tags=list(tags or []),
    )
    return build_wechat_description(draft)


def _is_video_file_input(candidate: Locator) -> bool:
    try:
        accept = (candidate.get_attribute("accept") or "").lower()
        if not accept:
            return True
        if "video" in accept or "mp4" in accept:
            return True
        if "image" in accept and "video" not in accept:
            return False
        return True
    except Exception:
        return True


def _locate_wechat_video_file_input(page: Page) -> Locator | None:
    """File inputs on WeChat are usually hidden; attached is enough for set_input_files."""
    try:
        page.wait_for_selector('input[type="file"]', state="attached", timeout=5000)
    except Exception:
        pass

    for selector in WECHAT_VIDEO_FILE_SELECTORS:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(min(count, 8)):
            candidate = locator.nth(index)
            try:
                if not _is_video_file_input(candidate):
                    continue
                return candidate
            except Exception:
                continue
    return None


def ensure_wechat_upload_surface(page: Page, *, timeout_ms: int) -> bool:
    deadline = time.time() + min(timeout_ms, 45_000) / 1000
    while time.time() < deadline:
        if _locate_wechat_video_file_input(page) is not None:
            return True
        for text in UPLOAD_TRIGGER_TEXTS:
            try:
                trigger = page.get_by_text(text, exact=False).first
                if trigger.is_visible(timeout=800):
                    human_click_element(page, trigger, timeout_ms=3000)
                    human_pause(page, "after_click")
                    break
            except Exception:
                continue
        human_pause(page, "polling")
    return _locate_wechat_video_file_input(page) is not None


def upload_wechat_video(page: Page, video_path: str, *, timeout_ms: int) -> bool:
    ensure_wechat_upload_surface(page, timeout_ms=min(timeout_ms, 45_000))

    deadline = time.time() + min(timeout_ms, 60_000) / 1000
    last_error: Exception | str | None = None
    while time.time() < deadline:
        file_input = _locate_wechat_video_file_input(page)
        if file_input is None:
            human_pause(page, "polling")
            continue
        try:
            human_upload_file(page, file_input, video_path, timeout_ms=15_000)
            logger.info("WeChat video file selected: %s", Path(video_path).name)
            return True
        except Exception as exc:
            last_error = exc
            logger.warning("WeChat video upload attempt failed: %s", exc)
            human_pause(page, "polling")

    for selector in ('wujie-app >> input[type="file"]', 'input[type="file"]'):
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            human_upload_file(page, locator, video_path, timeout_ms=15_000)
            logger.info("WeChat video uploaded via fallback selector: %s", selector)
            return True
        except Exception as exc:
            last_error = exc
            logger.warning("WeChat video upload fallback (%s) failed: %s", selector, exc)

    logger.warning("WeChat video file input not found: %s", last_error)
    return False


def _probe_wechat_upload_state(page: Page) -> dict[str, bool]:
    try:
        return page.evaluate(
            """() => {
                const seen = new Set();
                const texts = [];
                const buttons = [];
                let hasTitle = false;
                let hasDescEditor = false;
                let hasVideoPreview = false;
                const walk = (root) => {
                    if (!root || seen.has(root)) return;
                    seen.add(root);
                    if (root.innerText) texts.push(root.innerText);
                    else if (root.textContent) texts.push(root.textContent);
                    if (root.querySelector) {
                        if (root.querySelector(
                            'textarea[placeholder*="标题"], input[placeholder*="标题"]'
                        )) hasTitle = true;
                        if (root.querySelector(
                            '.post-desc-box .input-editor, div.input-editor[data-placeholder="添加描述"]'
                        )) hasDescEditor = true;
                        if (root.querySelector(
                            'video, [class*="video-preview"], [class*="player"], [class*="preview-video"]'
                        )) hasVideoPreview = true;
                    }
                    if (root.querySelectorAll) {
                        for (const btn of root.querySelectorAll('button')) buttons.push(btn);
                        for (const node of root.querySelectorAll('*')) {
                            if (node.shadowRoot) walk(node.shadowRoot);
                        }
                    }
                    if (root.shadowRoot) walk(root.shadowRoot);
                };
                walk(document.body);
                const wujie = document.querySelector('wujie-app');
                if (wujie) walk(wujie);
                const text = texts.join(' ').replace(/\\s+/g, ' ');
                const stillUploading = /上传中|正在上传|解析中|转码|处理中/.test(text);
                const uploadRequired = /请上传视频/.test(text);
                const editorReady = /添加描述|声明原创|更换封面|编辑封面|设置封面/.test(text);
                const publishBtn = buttons.find((btn) => {
                    const label = (btn.textContent || '').replace(/\\s+/g, '').trim();
                    return label === '发表' || label === '发布';
                });
                const publishEnabled = !!publishBtn
                    && !publishBtn.disabled
                    && !(publishBtn.className || '').includes('disabled');
                return {
                    stillUploading,
                    uploadRequired,
                    hasTitle,
                    hasDescEditor,
                    hasVideoPreview,
                    editorReady,
                    publishEnabled,
                };
            }"""
        )
    except Exception:
        return {}


def is_wechat_upload_blocked(page: Page) -> bool:
    state = _probe_wechat_upload_state(page)
    if state.get("uploadRequired") and not state.get("hasVideoPreview"):
        return True
    try:
        if page.get_by_text(WECHAT_UPLOAD_REQUIRED_PATTERN).first.is_visible(timeout=500):
            return True
    except Exception:
        pass
    return False


def _is_wechat_editor_ready(page: Page) -> bool:
    if _first_visible_locator(page, TITLE_SELECTORS) is not None:
        return True
    if _locate_post_desc_editor(page) is not None:
        return True
    return False


def wait_for_wechat_video_ready(page: Page, *, timeout_ms: int) -> bool:
    capped_ms = min(timeout_ms, WECHAT_VIDEO_READY_MAX_MS)
    deadline = time.time() + capped_ms / 1000
    while time.time() < deadline:
        state = _probe_wechat_upload_state(page)
        editor_visible = bool(
            state.get("hasTitle")
            or state.get("hasDescEditor")
            or state.get("editorReady")
            or _is_wechat_editor_ready(page)
        )
        video_attached = state.get("hasVideoPreview") or not state.get("uploadRequired")
        if editor_visible and video_attached and not state.get("stillUploading"):
            logger.info("WeChat video ready for publishing")
            return True
        if editor_visible and state.get("publishEnabled") and not state.get("stillUploading"):
            logger.info("WeChat publish button enabled after upload")
            return True
        human_pause(page, "polling")

    ready = _is_wechat_editor_ready(page) and not is_wechat_upload_blocked(page)
    if not ready:
        logger.warning("WeChat video ready wait timed out after %sms", capped_ms)
    return ready


def _is_topic_field(locator: Locator) -> bool:
    try:
        hint = locator.evaluate(
            """(el) => {
                const parts = [
                    el.getAttribute('placeholder'),
                    el.getAttribute('data-placeholder'),
                    el.getAttribute('aria-placeholder'),
                    el.className || '',
                ];
                return parts.filter(Boolean).join(' ').toLowerCase();
            }"""
        )
    except Exception:
        return False
    lowered = str(hint).lower()
    return any(token in lowered for token in _TOPIC_HINTS)


def _set_field_text(page: Page, locator: Locator, text: str) -> None:
    human_fill(page, locator, text)


def _set_contenteditable_text(locator: Locator, text: str) -> None:
    locator.evaluate(
        """(el, value) => {
            el.focus();
            const lines = String(value || '').split('\\n');
            const html = lines
                .map((line) => `<div>${line.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>`)
                .join('');
            el.innerHTML = html || '<div><br></div>';
            el.dispatchEvent(new InputEvent('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        text,
    )


def _first_visible_locator(page: Page, selectors: tuple[str, ...]) -> Locator | None:
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(min(count, 8)):
            candidate = locator.nth(index)
            try:
                if not candidate.is_visible():
                    continue
            except Exception:
                continue
            if _is_topic_field(candidate):
                continue
            return candidate
    return None


def _locate_post_desc_editor(page: Page) -> Locator | None:
    for selector in POST_DESC_EDITOR_SELECTORS:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(min(count, 4)):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
    return None


def _locate_description(page: Page) -> Locator | None:
    editor = _locate_post_desc_editor(page)
    if editor is not None:
        return editor

    for placeholder in DESCRIPTION_PLACEHOLDERS:
        locator = page.get_by_placeholder(re.compile(re.escape(placeholder)))
        count = locator.count()
        for index in range(min(count, 5)):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible() and not _is_topic_field(candidate):
                    return candidate
            except Exception:
                continue

    found = _first_visible_locator(page, DESCRIPTION_SELECTORS)
    if found is not None:
        return found

    textareas = page.locator("textarea:visible")
    if textareas.count() >= 2:
        return textareas.nth(1)
    return None


def fill_wechat_title(page: Page, title: str, *, timeout_ms: int, max_length: int = 30) -> bool:
    text = normalize_wechat_title(title, max_title_length=max_length)
    if not text:
        return False
    title_loc = _first_visible_locator(page, TITLE_SELECTORS)
    if title_loc is None:
        title_loc = page.locator(TITLE_SELECTORS[-1]).first
    try:
        title_loc.wait_for(state="visible", timeout=timeout_ms)
        _set_field_text(page, title_loc, text)
        return True
    except Exception as exc:
        logger.warning(f"Fill WeChat title failed: {exc}")
        return False


def fill_wechat_cover(page: Page, cover_path: Path, *, timeout_ms: int) -> bool:
    if not cover_path.is_file():
        logger.warning(f"WeChat cover file missing: {cover_path}")
        return False

    for text in COVER_TRIGGER_TEXTS:
        try:
            trigger = page.get_by_text(text, exact=False).first
            if trigger.is_visible(timeout=1500):
                human_click_element(page, trigger, timeout_ms=3000)
                human_pause(page, "after_click")
                break
        except Exception:
            continue

    for selector in COVER_FILE_SELECTORS:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(min(count, 6)):
            candidate = locator.nth(index)
            try:
                accept = (candidate.get_attribute("accept") or "").lower()
                if "video" in accept:
                    continue
                human_upload_file(page, candidate, str(cover_path.resolve()), timeout_ms=timeout_ms)
                logger.info("WeChat cover uploaded: %s", cover_path.name)
                return True
            except Exception:
                continue

    file_inputs = page.locator('input[type="file"]')
    if file_inputs.count() >= 2:
        try:
            human_upload_file(page, file_inputs.nth(1), str(cover_path.resolve()), timeout_ms=timeout_ms)
            logger.info("WeChat cover uploaded via fallback file input: %s", cover_path.name)
            return True
        except Exception as exc:
            logger.warning(f"Fill WeChat cover failed: {exc}")
            return False

    logger.warning("WeChat cover upload input not found")
    return False


def fill_wechat_post_description(
    page: Page,
    *,
    main_line2: str = "",
    sub_title: str = "",
    sub_title2: str = "",
    summary: str = "",
    tags: list[str] | None = None,
    description: str | None = None,
    timeout_ms: int,
) -> bool:
    text = compose_post_desc_text(
        main_line2=main_line2,
        sub_title=sub_title,
        sub_title2=sub_title2,
        summary=summary,
        tags=tags,
        description=description,
    )
    if not text:
        return False
    return fill_wechat_description(page, text, timeout_ms=timeout_ms)


def _description_visible_text(locator: Locator) -> str:
    try:
        return str(
            locator.evaluate("(el) => String(el.innerText || el.textContent || '').trim()")
            or ""
        )
    except Exception:
        return ""


def _description_contains(locator: Locator, expected: str) -> bool:
    actual = "".join(_description_visible_text(locator).split())
    needle = "".join((expected or "").split())
    if not needle:
        return bool(actual)
    return needle[:16] in actual


def wechat_description_present(page: Page, expected: str = "") -> bool:
    desc_loc = _locate_description(page)
    if desc_loc is None:
        return False
    if expected:
        return _description_contains(desc_loc, expected)
    return bool(_description_visible_text(desc_loc))


def fill_wechat_description(page: Page, description: str, *, timeout_ms: int) -> bool:
    if not description:
        return False
    deadline_attempts = max(3, timeout_ms // 3000)
    last_error: Exception | None = None
    for _ in range(deadline_attempts):
        desc_loc = _locate_description(page)
        if desc_loc is None:
            human_pause(page, "after_click")
            continue
        try:
            desc_loc.wait_for(state="visible", timeout=3000)
            # innerHTML + synthetic input does not update WeChat's editor document.
            # Publish serializes that document, so the live video ends up with no description.
            human_type_text(page, desc_loc, description, clear_first=True, timeout_ms=timeout_ms)
            if _description_contains(desc_loc, description):
                logger.info(
                    "WeChat post description filled and verified (%d chars)",
                    len(description),
                )
                return True
            logger.warning("WeChat description still empty after keyboard fill, retrying")
        except Exception as exc:
            last_error = exc
            human_pause(page, "after_click")
    logger.warning(f"Fill WeChat description failed: {last_error}")
    return False


def ensure_wechat_description(page: Page, description: str, *, timeout_ms: int) -> bool:
    if not description:
        return False
    if wechat_description_present(page, description):
        logger.info("WeChat post description still present after later form steps")
        return True
    logger.warning("WeChat description missing after later form steps, refilling")
    return fill_wechat_description(page, description, timeout_ms=timeout_ms)


def _ant_checkbox_checked(label_locator: Locator) -> bool:
    try:
        checkbox = label_locator.locator("span.ant-checkbox").first
        classes = checkbox.get_attribute("class") or ""
        if "ant-checkbox-checked" in classes:
            return True
        input_el = label_locator.locator("input.ant-checkbox-input").first
        return input_el.is_checked()
    except Exception:
        return False


def _locate_declare_original_checkbox(page: Page) -> Locator | None:
    for selector in DECLARE_ORIGINAL_SECTION_SELECTORS:
        section = page.locator(selector)
        if section.count() == 0:
            continue
        candidate = section.first.locator("label.ant-checkbox-wrapper").first
        try:
            if candidate.is_visible():
                return candidate
        except Exception:
            continue
    try:
        label = page.locator("label.ant-checkbox-wrapper").filter(
            has=page.locator("span", has_text="声明原创")
        ).first
        if label.is_visible():
            return label
    except Exception:
        pass
    return None


def _locate_original_dialog(page: Page) -> Locator | None:
    dialogs = page.locator(".weui-desktop-dialog").filter(
        has=page.locator(".weui-desktop-dialog__title", has_text=ORIGINAL_DIALOG_TITLE)
    )
    count = dialogs.count()
    for index in range(count - 1, -1, -1):
        candidate = dialogs.nth(index)
        try:
            if candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


def declare_wechat_original(page: Page, *, timeout_ms: int) -> bool:
    """Check 声明原创, accept protocol in dialog, and confirm."""
    try:
        main_label = _locate_declare_original_checkbox(page)
        if main_label is None:
            logger.warning("WeChat declare-original checkbox not found")
            return False

        main_label.scroll_into_view_if_needed(timeout=min(timeout_ms, 10_000))
        if _ant_checkbox_checked(main_label):
            logger.info("WeChat original already declared")
            return True

        human_click_element(page, main_label, timeout_ms=5000)
        human_pause(page, "after_click")

        dialog = _locate_original_dialog(page)
        if dialog is None:
            dialog = page.locator(".weui-desktop-dialog").filter(
                has=page.locator(".weui-desktop-dialog__title", has_text=ORIGINAL_DIALOG_TITLE)
            ).last
            dialog.wait_for(state="visible", timeout=min(timeout_ms, 10_000))

        proto_label = dialog.locator(".original-proto-wrapper label.ant-checkbox-wrapper").first
        proto_label.wait_for(state="visible", timeout=min(timeout_ms, 10_000))
        if not _ant_checkbox_checked(proto_label):
            human_click_element(page, proto_label, timeout_ms=5000)
            human_pause(page, "modal")

        confirm_btn = dialog.locator("button.weui-desktop-btn_primary").filter(has_text="声明原创")
        confirm_btn.wait_for(state="visible", timeout=min(timeout_ms, 10_000))
        for _ in range(20):
            classes = confirm_btn.get_attribute("class") or ""
            if "disabled" not in classes:
                break
            human_pause(page, "after_click")
        human_click_element(page, confirm_btn, timeout_ms=5000)
        human_pause(page, "after_click")

        if _ant_checkbox_checked(main_label):
            logger.info("WeChat original declaration confirmed")
            return True

        logger.warning("WeChat original dialog closed but checkbox state unclear")
        return True
    except Exception as exc:
        logger.warning(f"Declare WeChat original failed: {exc}")
        return False


WECHAT_PUBLISH_BUTTON_SELECTORS = (
    'wujie-app >> button:has-text("发表")',
    'wujie-app >> button:has-text("发布")',
    'button:has-text("发表")',
    'button:has-text("发布")',
)


WECHAT_PUBLISH_SUCCESS_PATTERN = re.compile(
    r"发表成功|发布成功|已发表|发表完成|提交成功|已提交",
    re.I,
)
WECHAT_PUBLISH_SUCCESS_URL_HINTS = (
    "platform/post/list",
    "platform/post/manage",
    "platform/content",
)


def click_wechat_publish(page: Page, *, timeout_ms: int) -> bool:
    from services.publishing.adapters.publish_button_helpers import click_publish_and_wait

    capped_ms = min(timeout_ms, 90_000)
    per_attempt_ms = min(capped_ms, 60_000)
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        if is_wechat_upload_blocked(page):
            logger.warning(
                "WeChat shows upload-required prompt before publish (attempt %s/%s)",
                attempt,
                max_attempts,
            )
            if not wait_for_wechat_video_ready(page, timeout_ms=per_attempt_ms):
                human_pause(page, "after_upload")
                continue
        elif not wait_for_wechat_video_ready(page, timeout_ms=min(per_attempt_ms, 30_000)):
            logger.warning("WeChat video may still be processing before publish click")

        published = click_publish_and_wait(
            page,
            timeout_ms=per_attempt_ms,
            button_texts=("发表", "发布"),
            extra_selectors=WECHAT_PUBLISH_BUTTON_SELECTORS,
            success_pattern=WECHAT_PUBLISH_SUCCESS_PATTERN,
            success_url_hints=WECHAT_PUBLISH_SUCCESS_URL_HINTS,
        )
        if published:
            return True

        if is_wechat_upload_blocked(page) and attempt < max_attempts:
            logger.warning(
                "WeChat publish blocked by missing video, retrying after upload wait"
            )
            wait_for_wechat_video_ready(page, timeout_ms=per_attempt_ms)
            human_pause(page, "polling")
            continue
        break

    return False
