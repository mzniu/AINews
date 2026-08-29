"""Helpers for filling Xiaohongshu creator center publish form."""
from __future__ import annotations

import re
import random
from typing import TYPE_CHECKING

from loguru import logger

from services.publishing.human_form import human_click_element
from services.publishing.human_pacing import human_pause
from services.publishing.human_interaction import (
    human_click,
    human_click_publish_target,
    human_idle_on_page,
    human_type_text,
)

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

VIDEO_TAB_TEXTS = ("上传视频",)

FILE_INPUT_SELECTORS = (
    "input.upload-input",
    'input[type="file"][accept*="video"]',
    'input[type="file"][accept*="mp4"]',
    'input[type="file"]',
)

TITLE_SELECTORS = (
    'div.edit-container input[type="text"]',
    'input[placeholder*="标题"]',
    ".titleInput input",
    ".titleInput .d-text",
)

DESCRIPTION_SELECTORS = (
    "#quillEditor.ql-editor",
    "#quillEditor .ql-editor",
    'div[contenteditable="true"][data-placeholder*="描述"]',
    'div[contenteditable="true"]',
)

COVER_READY_SELECTORS = (
    ".cover-container .preview-new",
    ".cover-container .reupload",
    ".cover-container .preview",
)


def normalize_xiaohongshu_title(title: str, *, max_length: int = 20) -> str:
    text = (title or "").strip()
    if len(text) > max_length:
        return text[:max_length]
    return text


def format_xiaohongshu_tags(tags: list[str]) -> str:
    parts: list[str] = []
    for raw in tags:
        tag = str(raw).strip().lstrip("#")
        if tag:
            parts.append(f"#{tag}")
    return " ".join(parts)


def compose_xiaohongshu_description(description: str, tags: list[str]) -> str:
    body = (description or "").strip()
    tags_line = format_xiaohongshu_tags(tags)
    if tags_line and body:
        return f"{body}\n{tags_line}"
    if tags_line:
        return tags_line
    return body


def _set_field_text(locator: Locator, text: str) -> None:
    human_type_text(locator.page, locator, text, clear_first=True)


def _first_visible_locator(page: Page, selectors: tuple[str, ...]) -> Locator | None:
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(min(count, 8)):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
    return None


def ensure_video_publish_tab(page: Page, *, timeout_ms: int = 15_000) -> bool:
    for text in VIDEO_TAB_TEXTS:
        try:
            tab = page.get_by_text(text, exact=True).first
            if tab.is_visible(timeout=1500):
                human_click(page, tab)
                return True
        except Exception:
            continue
    try:
        tab = page.locator("div.creator-tab").filter(has_text="上传视频").first
        if tab.is_visible(timeout=timeout_ms):
            human_click(page, tab)
            return True
    except Exception:
        pass
    return False


def ensure_upload_surface(page: Page, *, timeout_ms: int) -> bool:
    file_input = _first_visible_locator(page, FILE_INPUT_SELECTORS)
    if file_input is not None:
        return True
    for text in ("上传视频", "点击上传", "拖拽视频", "上传"):
        try:
            trigger = page.get_by_text(text, exact=False).first
            if trigger.is_visible(timeout=1500):
                human_click(page, trigger)
                if _first_visible_locator(page, FILE_INPUT_SELECTORS) is not None:
                    return True
        except Exception:
            continue
    try:
        page.wait_for_selector(FILE_INPUT_SELECTORS[0], state="attached", timeout=timeout_ms)
        return True
    except Exception:
        return False


def upload_xiaohongshu_video(page: Page, video_path: str, *, timeout_ms: int) -> bool:
    ensure_video_publish_tab(page, timeout_ms=min(timeout_ms, 15_000))
    if not ensure_upload_surface(page, timeout_ms=min(timeout_ms, 30_000)):
        logger.warning("Xiaohongshu upload surface not found")
        return False
    file_input = _first_visible_locator(page, FILE_INPUT_SELECTORS)
    if file_input is None:
        file_input = page.locator(FILE_INPUT_SELECTORS[-1]).first
    try:
        human_idle_on_page(page, moves=1)
        file_input.set_input_files(video_path, timeout=timeout_ms)
        human_pause(page, "after_upload")
        human_idle_on_page(page, moves=2)
        return True
    except Exception as exc:
        logger.warning(f"Xiaohongshu video upload failed: {exc}")
        return False


def wait_for_xiaohongshu_video_ready(page: Page, *, timeout_ms: int) -> bool:
    deadline_attempts = max(5, timeout_ms // 3000)
    for _ in range(deadline_attempts):
        for selector in COVER_READY_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
        try:
            if page.get_by_text(re.compile(r"上传成功|上传完成", re.I)).first.is_visible(timeout=1000):
                return True
        except Exception:
            pass
        human_pause(page, "polling")
        if random.random() < 0.35:
            human_idle_on_page(page, moves=1)
    return False


def wait_for_xiaohongshu_editor(page: Page, *, timeout_ms: int) -> bool:
    deadline_attempts = max(3, timeout_ms // 5000)
    for _ in range(deadline_attempts):
        if _first_visible_locator(page, TITLE_SELECTORS) is not None:
            return True
        human_pause(page, "polling")
    return False


def fill_xiaohongshu_title(page: Page, title: str, *, timeout_ms: int, max_length: int = 20) -> bool:
    text = normalize_xiaohongshu_title(title, max_length=max_length)
    if not text:
        return False
    title_loc = _first_visible_locator(page, TITLE_SELECTORS)
    if title_loc is None:
        for placeholder in ("填写标题", "标题"):
            locator = page.get_by_placeholder(re.compile(re.escape(placeholder)))
            if locator.count() > 0:
                title_loc = locator.first
                break
    if title_loc is None:
        return False
    try:
        title_loc.wait_for(state="visible", timeout=timeout_ms)
        human_idle_on_page(page, moves=1)
        _set_field_text(title_loc, text)
        return True
    except Exception as exc:
        logger.warning(f"Fill Xiaohongshu title failed: {exc}")
        return False


def fill_xiaohongshu_description(page: Page, description: str, *, timeout_ms: int) -> bool:
    if not description:
        return False
    desc_loc = _first_visible_locator(page, DESCRIPTION_SELECTORS)
    if desc_loc is None:
        for placeholder in ("描述", "正文", "说点什么"):
            locator = page.get_by_placeholder(re.compile(re.escape(placeholder)))
            if locator.count() > 0:
                desc_loc = locator.first
                break
    if desc_loc is None:
        return False
    try:
        desc_loc.wait_for(state="visible", timeout=timeout_ms)
        human_idle_on_page(page, moves=1)
        _set_field_text(desc_loc, description)
        return True
    except Exception as exc:
        logger.warning(f"Fill Xiaohongshu description failed: {exc}")
        return False


XHS_PUBLISH_INVOKE_METHODS = (
    "_onPublish",
    "_onSubmit",
    "onPublish",
    "_handlePublish",
)

XHS_PUBLISH_BUTTON_SELECTORS = (
    "xhs-publish-btn",
    ".publish-page-publish-btn button.bg-red",
    ".publish-page-publish-btn button",
    "button.publishBtn",
)

XHS_PUBLISH_SUCCESS_PATTERN = re.compile(
    r"发布成功|发布笔记成功|笔记发布成功|提交成功|已发布|笔记已提交|发布完成|"
    r"前往笔记管理|继续发布|继续创作|定时发布成功",
    re.I,
)

XHS_PUBLISH_FAILURE_PATTERN = re.compile(
    r"发布失败|提交失败|请添加话题|请填写标题|不能为空|字数超出|内容违规|请先上传",
    re.I,
)

XHS_PUBLISH_SUCCESS_URL_HINTS = (
    "note-manager",
    "note_manager",
    "notemanage",
    "/publish/success",
    "/new/home",
    "/creator/notes",
)


def _publish_label_matches(label: str) -> bool:
    text = re.sub(r"\s+", "", label or "")
    if not text:
        return True
    if text in {"发布", "定时发布"}:
        return True
    return text.startswith("发布")


def xhs_url_suggests_publish_success(initial_url: str, current_url: str) -> bool:
    if current_url == initial_url:
        return False
    if "/publish/success" in current_url:
        return True
    if any(hint in current_url for hint in ("note-manager", "note_manager", "notemanage")):
        return True
    if "/publish/publish" in initial_url:
        if "/new/" in current_url and "/publish/publish" not in current_url:
            return True
    return False


def wait_for_xhs_publish_button_ready(page: Page, *, timeout_ms: int) -> bool:
    deadline_attempts = max(5, timeout_ms // 3000)
    for _ in range(deadline_attempts):
        try:
            ready = page.evaluate(
                """() => {
                    const widgets = Array.from(document.querySelectorAll('xhs-publish-btn'));
                    for (const el of widgets) {
                        if (el.getAttribute('submit-disabled') === 'false') return true;
                        if (el.getAttribute('submit-disabled') !== 'true') return true;
                    }
                    const legacy = document.querySelector(
                        '.publish-page-publish-btn button.bg-red, button.publishBtn'
                    );
                    return Boolean(legacy && !legacy.disabled);
                }"""
            )
            if ready:
                return True
        except Exception:
            pass
        human_pause(page, "polling")
    return False


def _is_xhs_publish_target_enabled(locator: Locator) -> bool:
    try:
        if locator.evaluate(
            """(el) => {
                if (el.tagName && el.tagName.toLowerCase() === 'xhs-publish-btn') {
                    return el.getAttribute('submit-disabled') !== 'true';
                }
                return !el.disabled && el.getAttribute('aria-disabled') !== 'true';
            }"""
        ):
            return True
    except Exception:
        pass
    return False


def _locate_xhs_publish_targets(page: Page) -> list[Locator]:
    targets: list[Locator] = []
    widget = page.locator("xhs-publish-btn").first
    if widget.count() > 0:
        inner = widget.locator("button").first
        if inner.count() > 0:
            targets.append(inner)
        targets.append(widget)
    for selector in (
        ".publish-page-publish-btn button.bg-red",
        ".publish-page-publish-btn button",
        "button.publishBtn",
    ):
        locator = page.locator(selector)
        count = min(locator.count(), 4)
        for index in range(count):
            targets.append(locator.nth(index))
    return targets


def scroll_xhs_publish_into_view(page: Page) -> None:
    try:
        page.evaluate(
            """() => {
                const el = document.querySelector('xhs-publish-btn');
                if (el) el.scrollIntoView({ block: 'end', behavior: 'instant' });
                window.scrollTo(0, document.body.scrollHeight);
            }"""
        )
        human_pause(page, "after_click")
    except Exception:
        pass


def _invoke_xhs_publish_widget(page: Page) -> bool:
    """Trigger publish on closed-shadow xhs-publish-btn via exposed component methods."""
    try:
        result = page.evaluate(
            """(publishNames) => {
                const isWidgetReady = (el) => {
                    if (!el) return false;
                    if (el.getAttribute('submit-loading') === 'true') return false;
                    if (el.getAttribute('submit-disabled') === 'true') return false;
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return false;
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || 1) > 0;
                };
                const widgets = Array.from(document.querySelectorAll('xhs-publish-btn'))
                    .filter(isWidgetReady);
                for (const el of widgets) {
                    el.scrollIntoView({ block: 'end', behavior: 'instant' });
                    for (const name of publishNames) {
                        const fn = el[name];
                        if (typeof fn === 'function') {
                            fn.call(el);
                            return { ok: true, method: name };
                        }
                    }
                }
                return { ok: false };
            }""",
            list(XHS_PUBLISH_INVOKE_METHODS),
        )
        if result and result.get("ok"):
            logger.info("Xiaohongshu publish invoked via {}", result.get("method"))
            human_pause(page, "after_click")
            return True
    except Exception as exc:
        logger.debug("Xiaohongshu publish invoke failed: {}", exc)
    return False


def _click_xhs_publish_via_keyboard(page: Page) -> bool:
    """Focus the web component and Tab to the red publish button inside closed shadow."""
    try:
        widget = page.locator("xhs-publish-btn").first
        if widget.count() == 0 or not widget.is_visible(timeout=1500):
            return False
        widget.scroll_into_view_if_needed(timeout=5000)
        human_click_element(page, widget, timeout_ms=3000)
        human_pause(page, "before_publish")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        page.keyboard.press("Enter")
        logger.info("Xiaohongshu publish triggered via keyboard focus")
        human_pause(page, "after_click")
        return True
    except Exception as exc:
        logger.debug("Xiaohongshu keyboard publish failed: {}", exc)
    return False


def _click_xhs_publish_component(page: Page) -> bool:
    """Click publish: component invoke → keyboard → legacy visible button."""
    scroll_xhs_publish_into_view(page)
    if _invoke_xhs_publish_widget(page):
        return True
    if _click_xhs_publish_via_keyboard(page):
        return True
    for target in _locate_xhs_publish_targets(page):
        try:
            if not target.is_visible(timeout=1200):
                continue
            label = (target.inner_text(timeout=1000) or "").strip()
            if label and not _publish_label_matches(label):
                continue
            if not _is_xhs_publish_target_enabled(target):
                continue
            if human_click_publish_target(page, target):
                logger.info("Xiaohongshu publish clicked via human mouse")
                return True
        except Exception as exc:
            logger.debug("Xiaohongshu publish target skipped: {}", exc)
    return False


def wait_for_xiaohongshu_publish_success(
    page: Page,
    *,
    timeout_ms: int,
    initial_url: str,
) -> bool:
    from services.publishing.adapters.publish_button_helpers import wait_for_publish_success

    return wait_for_publish_success(
        page,
        timeout_ms=timeout_ms,
        success_pattern=XHS_PUBLISH_SUCCESS_PATTERN,
        failure_pattern=XHS_PUBLISH_FAILURE_PATTERN,
        success_url_hints=XHS_PUBLISH_SUCCESS_URL_HINTS,
        initial_url=initial_url,
        url_success_checker=xhs_url_suggests_publish_success,
    )


def click_xiaohongshu_publish(page: Page, *, timeout_ms: int) -> bool:
    from services.publishing.adapters.publish_button_helpers import confirm_publish_dialogs

    initial_url = page.url
    human_pause(page, "before_publish")
    human_idle_on_page(page, moves=2)
    scroll_xhs_publish_into_view(page)
    wait_for_xhs_publish_button_ready(page, timeout_ms=min(timeout_ms, 60_000))

    clicked = False
    deadline_attempts = max(3, timeout_ms // 5000)
    for _ in range(deadline_attempts):
        if _click_xhs_publish_component(page):
            clicked = True
            break
        human_pause(page, "polling")
    if not clicked:
        try:
            fallback = page.get_by_role("button", name=re.compile(r"^发布")).last
            if fallback.is_visible(timeout=1500) and human_click_publish_target(page, fallback):
                clicked = True
        except Exception:
            pass
    if not clicked:
        return False

    poll_deadline = max(8, timeout_ms // 4000)
    for attempt in range(poll_deadline):
        confirm_publish_dialogs(page, timeout_ms=2500)
        if wait_for_xiaohongshu_publish_success(
            page,
            timeout_ms=2500,
            initial_url=initial_url,
        ):
            return True
        if attempt in {2, 5} and _click_xhs_publish_component(page):
            human_pause(page, "after_click")
        human_pause(page, "polling")

    return wait_for_xiaohongshu_publish_success(
        page,
        timeout_ms=timeout_ms,
        initial_url=initial_url,
    )
