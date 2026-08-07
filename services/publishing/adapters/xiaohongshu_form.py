"""Helpers for filling Xiaohongshu creator center publish form."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

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
    locator.scroll_into_view_if_needed(timeout=5000)
    locator.click(timeout=5000)
    tag_name = locator.evaluate("(el) => el.tagName")
    if tag_name in {"TEXTAREA", "INPUT"}:
        locator.fill(text)
        locator.evaluate(
            """(el) => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }"""
        )
        return
    locator.evaluate(
        """(el, value) => {
            el.focus();
            if ('value' in el) {
                el.value = value;
            }
            el.textContent = value;
            el.innerText = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
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
                tab.click(timeout=3000)
                page.wait_for_timeout(800)
                return True
        except Exception:
            continue
    try:
        tab = page.locator("div.creator-tab").filter(has_text="上传视频").first
        if tab.is_visible(timeout=timeout_ms):
            tab.click(timeout=3000)
            page.wait_for_timeout(800)
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
                trigger.click(timeout=3000)
                page.wait_for_timeout(1000)
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
        file_input.set_input_files(video_path, timeout=timeout_ms)
        page.wait_for_timeout(2000)
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
        page.wait_for_timeout(2000)
    return False


def wait_for_xiaohongshu_editor(page: Page, *, timeout_ms: int) -> bool:
    deadline_attempts = max(3, timeout_ms // 5000)
    for _ in range(deadline_attempts):
        if _first_visible_locator(page, TITLE_SELECTORS) is not None:
            return True
        page.wait_for_timeout(2000)
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
        _set_field_text(desc_loc, description)
        return True
    except Exception as exc:
        logger.warning(f"Fill Xiaohongshu description failed: {exc}")
        return False


XHS_PUBLISH_BUTTON_SELECTORS = (
    "xhs-publish-btn",
    ".publish-page-publish-btn button.bg-red",
    ".publish-page-publish-btn button",
    "button.publishBtn",
)


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
        page.wait_for_timeout(2000)
    return False


def _click_xhs_publish_component(page: Page) -> bool:
    try:
        result = page.evaluate(
            """() => {
                const publishNames = ['_onPublish', '_onSubmit', 'onPublish', '_handlePublish'];
                const widgets = Array.from(document.querySelectorAll('xhs-publish-btn'));
                for (const el of widgets) {
                    if (el.getAttribute('submit-disabled') === 'true') continue;
                    for (const name of publishNames) {
                        if (typeof el[name] === 'function') {
                            el[name]();
                            return { ok: true, method: name };
                        }
                    }
                }
                const legacySelectors = [
                    '.publish-page-publish-btn button.bg-red',
                    '.publish-page-publish-btn button',
                    'button.publishBtn',
                ];
                for (const selector of legacySelectors) {
                    const buttons = Array.from(document.querySelectorAll(selector));
                    for (const btn of buttons) {
                        const text = (btn.textContent || '').trim();
                        if (text !== '发布' || btn.disabled) continue;
                        btn.click();
                        return { ok: true, method: selector };
                    }
                }
                return { ok: false };
            }"""
        )
    except Exception as exc:
        logger.warning("Xiaohongshu publish component click failed: %s", exc)
        return False
    if result and result.get("ok"):
        logger.info("Xiaohongshu publish triggered via %s", result.get("method"))
        return True
    return False


def click_xiaohongshu_publish(page: Page, *, timeout_ms: int) -> bool:
    from services.publishing.adapters.publish_button_helpers import (
        confirm_publish_dialogs,
        wait_for_publish_success,
    )

    wait_for_xhs_publish_button_ready(page, timeout_ms=min(timeout_ms, 60_000))

    clicked = False
    deadline_attempts = max(3, timeout_ms // 5000)
    for _ in range(deadline_attempts):
        if _click_xhs_publish_component(page):
            clicked = True
            break
        page.wait_for_timeout(1500)
    if not clicked:
        return False

    for _ in range(4):
        confirm_publish_dialogs(page, timeout_ms=3000)
        page.wait_for_timeout(1200)

    return wait_for_publish_success(
        page,
        timeout_ms=timeout_ms,
        success_pattern=re.compile(r"发布成功|提交成功|笔记管理|审核中", re.I),
        success_url_hints=(
            "note-manager",
            "published",
            "success",
            "creator.xiaohongshu.com/new/home",
        ),
    )
