"""Helpers for filling Douyin creator center publish form."""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

FILE_INPUT_SELECTORS = (
    'input[type="file"][accept*="video"]',
    'input[type="file"][accept*="mp4"]',
    'input[type="file"]',
)

UPLOAD_TRIGGER_TEXTS = ("上传视频", "点击上传", "上传", "发布视频")

TITLE_SELECTORS = (
    'input[placeholder*="标题"]',
    'input[placeholder*="作品"]',
    'textarea[placeholder*="标题"]',
    '[contenteditable="true"][data-placeholder*="标题"]',
    '[contenteditable="true"]',
)

DESCRIPTION_SELECTORS = (
    'textarea[placeholder*="简介"]',
    'textarea[placeholder*="描述"]',
    'div[contenteditable="true"][data-placeholder*="简介"]',
    'div[contenteditable="true"][data-placeholder*="描述"]',
    '[contenteditable="true"]',
)

TOPIC_SELECTORS = (
    'input[placeholder*="话题"]',
    'input[placeholder*="添加话题"]',
    'input[placeholder*="搜索"]',
)

AI_COVER_CONTAINER_SELECTORS = (
    '[class*="recommendCoverContainer"]',
    '[class*="recommendContainer"]',
    '[class*="recommendDisplay"]',
)

RECOMMEND_COVER_CONTAINER_SELECTOR = 'div[class*="recommendCoverContainer"]'
RECOMMEND_COVER_ITEM_SELECTOR = (
    'div[class*="recommendCoverContainer"] > div[class*="recommendCover"]'
)
AI_COVER_ITEM_SELECTOR = '[class*="recommendCover"]'
AI_COVER_MARKER_SELECTOR = '[class*="ai-"]'
AI_COVER_SELECTED_SELECTOR = '[class*="recommendCover"][class*="selected"]'

# Avoid bare "处理中" — it appears in unrelated UI and blocks readiness forever.
UPLOADING_PATTERN = re.compile(r"正在上传|上传中[\d%]|转码中|解析中|视频处理中", re.I)
VIDEO_READY_TEXTS = ("设置封面", "预览视频", "预览封面", "添加合集", "自主声明")

DOUYIN_VIDEO_READY_MAX_MS = 180_000
DOUYIN_EDITOR_READY_MAX_MS = 60_000
DOUYIN_COVER_SELECT_MAX_MS = 6_000
DOUYIN_PUBLISH_MAX_MS = 60_000


def normalize_douyin_title(title: str, *, max_length: int = 55) -> str:
    text = (title or "").strip().replace("！", "？")
    if len(text) > max_length:
        return text[:max_length]
    return text


def format_douyin_tags(tags: list[str]) -> str:
    parts: list[str] = []
    for raw in tags:
        tag = str(raw).strip().lstrip("#")
        if tag:
            parts.append(f"#{tag}")
    return " ".join(parts)


def _set_field_text(locator: Locator, text: str) -> None:
    locator.scroll_into_view_if_needed(timeout=5000)
    locator.click(timeout=5000)
    tag_name = locator.evaluate("(el) => el.tagName")
    if tag_name in {"TEXTAREA", "INPUT"}:
        locator.fill(text)
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


def ensure_upload_surface(page: Page, *, timeout_ms: int) -> bool:
    file_input = _first_visible_locator(page, FILE_INPUT_SELECTORS)
    if file_input is not None:
        return True
    for text in UPLOAD_TRIGGER_TEXTS:
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


def upload_douyin_video(page: Page, video_path: str, *, timeout_ms: int) -> bool:
    if not ensure_upload_surface(page, timeout_ms=min(timeout_ms, 30_000)):
        logger.warning("Douyin upload surface not found")
        return False
    file_input = _first_visible_locator(page, FILE_INPUT_SELECTORS)
    if file_input is None:
        file_input = page.locator(FILE_INPUT_SELECTORS[-1]).first
    try:
        file_input.set_input_files(video_path, timeout=timeout_ms)
        page.wait_for_timeout(2000)
        return True
    except Exception as exc:
        logger.warning(f"Douyin video upload failed: {exc}")
        return False


def wait_for_douyin_editor(page: Page, *, timeout_ms: int) -> bool:
    capped_ms = min(timeout_ms, DOUYIN_EDITOR_READY_MAX_MS)
    deadline = time.time() + capped_ms / 1000
    while time.time() < deadline:
        if _first_visible_locator(page, TITLE_SELECTORS) is not None:
            return True
        page.wait_for_timeout(1500)
    return False


def _locate_recommend_cover_in_container(page: Page) -> Locator | None:
    container = page.locator(RECOMMEND_COVER_CONTAINER_SELECTOR).first
    if container.count() == 0:
        return None
    try:
        if not container.is_visible(timeout=1500):
            return None
    except Exception:
        return None

    covers = container.locator(':scope > div[class*="recommendCover"]')
    count = covers.count()
    for index in range(min(count, 4)):
        cover = covers.nth(index)
        try:
            if not cover.is_visible():
                continue
            if cover.locator('[class*="noPic"]').count() > 0:
                continue
            return cover
        except Exception:
            continue

    fallback = page.locator(RECOMMEND_COVER_ITEM_SELECTOR).first
    if fallback.count() > 0:
        try:
            if fallback.is_visible(timeout=1000):
                return fallback
        except Exception:
            pass
    return None


def _locate_ai_recommend_cover(page: Page) -> Locator | None:
    return _locate_recommend_cover_in_container(page)


def _confirm_douyin_cover_modal(page: Page, *, timeout_ms: int = 3_000) -> bool:
    """Click 确定 on the '是否确认应用此封面？' semi-modal."""
    try:
        modal = page.locator(".semi-modal-content").filter(
            has=page.get_by_text("是否确认应用此封面", exact=False)
        ).last
        if not modal.is_visible(timeout=min(timeout_ms, 2000)):
            return False
        confirm_btn = modal.locator(
            ".semi-modal-footer button.semi-button-primary"
        ).filter(has_text="确定").first
        confirm_btn.click(timeout=3000)
        page.wait_for_timeout(500)
        logger.info("Douyin AI cover confirm modal accepted")
        return True
    except Exception:
        try:
            confirm = page.get_by_role("button", name="确定").last
            if confirm.is_visible(timeout=1000):
                confirm.click(timeout=3000)
                page.wait_for_timeout(500)
                logger.info("Douyin AI cover confirm modal accepted (fallback)")
                return True
        except Exception:
            pass
    return False


def select_douyin_ai_recommend_cover(page: Page, *, timeout_ms: int) -> bool:
    """Best-effort: click first recommend cover via JS (avoids Playwright action hangs)."""
    capped_ms = min(timeout_ms, DOUYIN_COVER_SELECT_MAX_MS)
    deadline = time.time() + capped_ms / 1000
    while time.time() < deadline:
        try:
            result = page.evaluate(
                """() => {
                    const container = document.querySelector('div[class*="recommendCoverContainer"]');
                    if (!container) return { ok: false, reason: 'no-container' };
                    const covers = Array.from(
                        container.querySelectorAll(':scope > div[class*="recommendCover"]')
                    ).filter((node) => !node.querySelector('[class*="noPic"]'));
                    const cover = covers[0];
                    if (!cover) return { ok: false, reason: 'no-cover' };
                    if ((cover.className || '').includes('selected')) {
                        return { ok: true, reason: 'already-selected' };
                    }
                    cover.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    return { ok: true, reason: 'clicked' };
                }"""
            )
            reason = (result or {}).get("reason", "")
            if (result or {}).get("ok"):
                page.wait_for_timeout(400)
                _confirm_douyin_cover_modal(page, timeout_ms=1500)
                logger.info("Douyin recommend cover: %s", reason)
                return True
            logger.debug("Douyin cover probe: %s", reason)
        except Exception as exc:
            logger.debug("Douyin cover select probe failed: %s", exc)
        page.wait_for_timeout(800)

    logger.warning("Douyin recommend cover skipped after %sms (non-blocking)", capped_ms)
    return False


def fill_douyin_title(page: Page, title: str, *, timeout_ms: int, max_length: int = 55) -> bool:
    text = normalize_douyin_title(title, max_length=max_length)
    if not text:
        return False
    title_loc = _first_visible_locator(page, TITLE_SELECTORS)
    if title_loc is None:
        return False
    try:
        title_loc.wait_for(state="visible", timeout=timeout_ms)
        _set_field_text(title_loc, text)
        return True
    except Exception as exc:
        logger.warning(f"Fill Douyin title failed: {exc}")
        return False


def fill_douyin_description(page: Page, description: str, *, timeout_ms: int) -> bool:
    if not description:
        return False
    desc_loc = _first_visible_locator(page, DESCRIPTION_SELECTORS)
    if desc_loc is None:
        for placeholder in ("简介", "描述", "说点什么"):
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
        logger.warning(f"Fill Douyin description failed: {exc}")
        return False


def fill_douyin_topics(page: Page, tags: list[str], *, timeout_ms: int) -> bool:
    topic_line = format_douyin_tags(tags)
    if not topic_line:
        return False
    topic_loc = _first_visible_locator(page, TOPIC_SELECTORS)
    if topic_loc is None:
        return False
    try:
        topic_loc.wait_for(state="visible", timeout=timeout_ms)
        _set_field_text(topic_loc, topic_line)
        return True
    except Exception as exc:
        logger.warning(f"Fill Douyin topics failed: {exc}")
        return False


DOUYIN_PUBLISH_BUTTON_SELECTORS = (
    'button[class*="primary"][class*="fixed"]:has-text("发布")',
    'button[class*="button-"][class*="primary-"]:has-text("发布")',
    'button:has-text("发布")',
)


def _probe_douyin_upload_state(page: Page) -> dict[str, bool]:
    """Inspect DOM for upload progress instead of scanning all body text."""
    try:
        return page.evaluate(
            """() => {
                const text = (document.body.textContent || '').replace(/\\s+/g, ' ');
                const stillUploading = /正在上传|上传中[\\d%]+|转码中|解析中|视频处理中/.test(text);
                const editorReady = /设置封面|预览视频|预览封面|添加合集|自主声明/.test(text);
                const hasTitle = !!document.querySelector(
                    'input[placeholder*="标题"], textarea[placeholder*="标题"], [contenteditable="true"][data-placeholder*="标题"]'
                );
                const hasCoverContainer = !!document.querySelector('div[class*="recommendCoverContainer"]');
                const hasPublishBtn = Array.from(document.querySelectorAll('button')).some((btn) => {
                    const label = (btn.textContent || '').replace(/\\s+/g, '').trim();
                    return label === '发布' || label === '立即发布';
                });
                return {
                    stillUploading,
                    editorReady,
                    hasTitle,
                    hasCoverContainer,
                    hasPublishBtn,
                };
            }"""
        )
    except Exception:
        return {}


def wait_for_douyin_video_ready(page: Page, *, timeout_ms: int) -> bool:
    capped_ms = min(timeout_ms, DOUYIN_VIDEO_READY_MAX_MS)
    deadline = time.time() + capped_ms / 1000
    while time.time() < deadline:
        state = _probe_douyin_upload_state(page)
        if state:
            editor_visible = (
                state.get("hasTitle")
                or state.get("hasCoverContainer")
                or state.get("editorReady")
            )
            if editor_visible and not state.get("stillUploading"):
                logger.info("Douyin video ready: editor visible, upload finished")
                return True
            if editor_visible and state.get("hasPublishBtn"):
                logger.info("Douyin video ready: publish button visible")
                return True
        page.wait_for_timeout(1500)
    logger.warning("Douyin video ready wait timed out after %sms", capped_ms)
    return False


def select_douyin_publish_cover(page: Page, *, timeout_ms: int) -> bool:
    return select_douyin_ai_recommend_cover(page, timeout_ms=timeout_ms)


def _click_bottom_douyin_publish_button(page: Page) -> bool:
    try:
        clicked = page.evaluate(
            """() => {
                const candidates = Array.from(
                    document.querySelectorAll('button, [role="button"], div[role="button"]')
                );
                const visible = candidates
                    .filter((node) => {
                        const text = (node.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (text !== '发布' && text !== '立即发布') return false;
                        const style = window.getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        const disabled = node.disabled || node.getAttribute('aria-disabled') === 'true';
                        return (
                            !disabled &&
                            style.visibility !== 'hidden' &&
                            style.display !== 'none' &&
                            rect.width > 0 &&
                            rect.height > 0
                        );
                    })
                    .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom);
                const target = visible[0];
                if (!target) return false;
                target.click();
                return true;
            }"""
        )
        if clicked:
            logger.info("Douyin publish clicked via bottom button scan")
            return True
    except Exception as exc:
        logger.warning("Douyin bottom publish scan failed: %s", exc)
    return False


def click_douyin_publish(page: Page, *, timeout_ms: int) -> bool:
    from services.publishing.adapters.publish_button_helpers import (
        click_publish_button,
        confirm_publish_dialogs,
        scroll_to_publish_area,
        wait_for_publish_success,
    )

    capped_ms = min(timeout_ms, DOUYIN_PUBLISH_MAX_MS)
    scroll_to_publish_area(page)

    clicked = _click_bottom_douyin_publish_button(page)
    if not clicked:
        clicked = click_publish_button(
            page,
            timeout_ms=min(capped_ms, 20_000),
            button_texts=("发布", "立即发布"),
            extra_selectors=DOUYIN_PUBLISH_BUTTON_SELECTORS,
            scroll_first=False,
        )
    if not clicked:
        deadline = time.time() + min(capped_ms, 15_000) / 1000
        while time.time() < deadline:
            if _click_bottom_douyin_publish_button(page):
                clicked = True
                break
            page.wait_for_timeout(1000)
    if not clicked:
        logger.warning("Douyin publish button not found")
        return False

    confirm_publish_dialogs(page, timeout_ms=5000)
    page.wait_for_timeout(800)
    confirm_publish_dialogs(page, timeout_ms=3000)
    success = wait_for_publish_success(
        page,
        timeout_ms=capped_ms,
        success_pattern=re.compile(r"发布成功|已发布|发布完成|作品管理|内容管理", re.I),
        success_url_hints=(
            "content/manage",
            "creator-micro/content/manage",
            "creator-micro/content/post",
        ),
    )
    if success:
        logger.info("Douyin publish success detected")
    else:
        logger.warning("Douyin publish clicked but success not confirmed within %sms", capped_ms)
    return success
