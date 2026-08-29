"""Helpers for filling Douyin creator center publish form."""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from loguru import logger

from services.publishing.human_form import (
    human_click_element,
    human_fill,
    human_upload_file,
)
from services.publishing.human_pacing import human_pause

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
    '[contenteditable="true"][placeholder*="标题"]',
    'div[class*="title"] [contenteditable="true"]',
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
DOUYIN_AI_COVER_WAIT_MAX_MS = 90_000
DOUYIN_COVER_SELECT_MAX_MS = 45_000
DOUYIN_PUBLISH_MAX_MS = 60_000

COVER_PANEL_ENTRY_TEXTS = ("设置封面", "更换封面", "选择封面", "编辑封面", "智能推荐封面")

_PROBE_DOUYIN_AI_COVERS_JS = """() => {
    const checking = !!document.querySelector('[class*="coverChecking"]');
    let container = document.querySelector('div[class*="recommendCoverContainer"]');
    if (!container) {
        const outer = document.querySelector('div[class*="recommendContainer"]');
        if (outer) {
            container =
                outer.querySelector('div[class*="recommendCoverContainer"]') || outer;
        }
    }
    if (!container) {
        return { ready: false, reason: 'no-container', checking };
    }
    const covers = Array.from(
        container.querySelectorAll('div[class*="recommendCover"]')
    ).filter((node) => {
        if (node.querySelector('[class*="noPic"]')) return false;
        const img = node.querySelector('img');
        return !!img && !!(img.currentSrc || img.src);
    });
    const aiCover = covers.find((node) => {
        const cls = (node.className || '').toLowerCase();
        return cls.includes('ai') || !!node.querySelector('[class*="ai-"]');
    });
    const aiSelected = !!(aiCover && (aiCover.className || '').includes('selected'));
    return {
        ready: !checking && !!aiCover,
        hasAi: !!aiCover,
        aiSelected,
        count: covers.length,
        checking,
        reason: checking ? 'cover-checking' : (aiCover ? 'ai-ready' : 'no-ai-cover'),
    };
}"""

_SELECT_DOUYIN_AI_COVER_JS = """() => {
    let container = document.querySelector('div[class*="recommendCoverContainer"]');
    if (!container) {
        const outer = document.querySelector('div[class*="recommendContainer"]');
        if (outer) {
            container =
                outer.querySelector('div[class*="recommendCoverContainer"]') || outer;
        }
    }
    if (!container) return { ok: false, reason: 'no-container' };
    const covers = Array.from(
        container.querySelectorAll('div[class*="recommendCover"]')
    ).filter((node) => {
        if (node.querySelector('[class*="noPic"]')) return false;
        const img = node.querySelector('img');
        return !!img && !!(img.currentSrc || img.src);
    });
    if (!covers.length) return { ok: false, reason: 'no-cover' };
    const aiCover = covers.find((node) => {
        const cls = (node.className || '').toLowerCase();
        return cls.includes('ai') || !!node.querySelector('[class*="ai-"]');
    });
    if (!aiCover) return { ok: false, reason: 'no-ai-cover' };
    if ((aiCover.className || '').includes('selected')) {
        return { ok: true, reason: 'ai-already-selected' };
    }
    aiCover.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    return { ok: true, reason: 'ai-clicked' };
}"""


def ai_cover_probe_is_ready(result: dict | None, *, require_ai: bool = True) -> bool:
    if not result:
        return False
    if result.get("checking"):
        return False
    if not result.get("count"):
        return False
    if require_ai:
        return bool(result.get("hasAi"))
    return True


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


def _set_field_text(page: Page, locator: Locator, text: str) -> None:
    human_fill(page, locator, text)


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
                human_click_element(page, trigger, timeout_ms=3000)
                human_pause(page, "after_click")
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
        human_upload_file(page, file_input, video_path, timeout_ms=timeout_ms)
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
        human_pause(page, "polling")
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
    preferred: Locator | None = None
    fallback: Locator | None = None
    for index in range(min(count, 6)):
        cover = covers.nth(index)
        try:
            if not cover.is_visible():
                continue
            if cover.locator('[class*="noPic"]').count() > 0:
                continue
            if fallback is None:
                fallback = cover
            class_name = cover.evaluate("(el) => el.className || ''") or ""
            has_ai_child = cover.locator(AI_COVER_MARKER_SELECTOR).count() > 0
            if "ai" in class_name.lower() or has_ai_child:
                preferred = cover
                break
        except Exception:
            continue

    if preferred is not None:
        return preferred
    if fallback is not None:
        return fallback

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


def _probe_douyin_ai_covers(page: Page) -> dict:
    try:
        return page.evaluate(_PROBE_DOUYIN_AI_COVERS_JS) or {}
    except Exception:
        return {}


def ensure_douyin_cover_panel_visible(page: Page) -> bool:
    """Scroll to cover area and click entry if recommend covers are hidden."""
    try:
        action = page.evaluate(
            """(texts) => {
                let container = document.querySelector('div[class*="recommendCoverContainer"]');
                if (!container) {
                    const outer = document.querySelector('div[class*="recommendContainer"]');
                    if (outer) {
                        container =
                            outer.querySelector('div[class*="recommendCoverContainer"]') || outer;
                    }
                }
                if (container) {
                    const rect = container.getBoundingClientRect();
                    container.scrollIntoView({ block: 'center', behavior: 'instant' });
                    if (rect.width > 0 && rect.height > 0) {
                        return 'container-visible';
                    }
                }
                for (const text of texts) {
                    const nodes = Array.from(
                        document.querySelectorAll('span, div, button, a, label')
                    ).filter((el) => {
                        const label = (el.textContent || '').replace(/\\s+/g, '').trim();
                        return label === text || label.startsWith(text);
                    });
                    for (const el of nodes) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            el.scrollIntoView({ block: 'center', behavior: 'instant' });
                            el.click();
                            return `clicked:${text}`;
                        }
                    }
                }
                const preview = document.querySelector(
                    '[class*="coverPreview"], [class*="coverContainer"], [class*="cover-container"]'
                );
                if (preview) {
                    preview.scrollIntoView({ block: 'center', behavior: 'instant' });
                    preview.click();
                    return 'clicked:preview';
                }
                return 'not-found';
            }""",
            list(COVER_PANEL_ENTRY_TEXTS),
        )
        logger.info("Douyin cover panel ensure: {}", action)
        human_pause(page, "after_click")
        return action != "not-found"
    except Exception as exc:
        logger.debug("Douyin cover panel ensure failed: {}", exc)
        return False


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
        human_click_element(page, confirm_btn, timeout_ms=3000)
        human_pause(page, "modal")
        logger.info("Douyin AI cover confirm modal accepted")
        return True
    except Exception:
        try:
            confirm = page.get_by_role("button", name="确定").last
            if confirm.is_visible(timeout=1000):
                human_click_element(page, confirm, timeout_ms=3000)
                human_pause(page, "modal")
                logger.info("Douyin AI cover confirm modal accepted (fallback)")
                return True
        except Exception:
            pass
    return False


def wait_for_douyin_ai_covers(page: Page, *, timeout_ms: int) -> bool:
    """Wait until Douyin shows AI recommend cover thumbnails (not just any cover)."""
    capped_ms = min(timeout_ms, DOUYIN_AI_COVER_WAIT_MAX_MS)
    deadline = time.time() + capped_ms / 1000
    ensure_douyin_cover_panel_visible(page)
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        if attempt % 4 == 0:
            ensure_douyin_cover_panel_visible(page)
        result = _probe_douyin_ai_covers(page)
        if ai_cover_probe_is_ready(result, require_ai=True):
            logger.info(
                "Douyin AI covers ready: count={} hasAi={} reason={}",
                result.get("count"),
                result.get("hasAi"),
                result.get("reason"),
            )
            return True
        reason = result.get("reason", "unknown")
        if result.get("count") and not result.get("hasAi"):
            logger.debug(
                "Douyin recommend covers visible but AI not ready: count={} reason={}",
                result.get("count"),
                reason,
            )
        else:
            logger.debug("Douyin AI cover wait: reason={}", reason)
        human_pause(page, "polling")
    logger.warning("Douyin AI covers not ready after {}ms", capped_ms)
    return False


def select_douyin_ai_recommend_cover(page: Page, *, timeout_ms: int) -> bool:
    """Select Douyin platform AI recommend cover (not local custom cover)."""
    capped_ms = min(timeout_ms, DOUYIN_COVER_SELECT_MAX_MS)
    deadline = time.time() + capped_ms / 1000
    while time.time() < deadline:
        probe = _probe_douyin_ai_covers(page)
        if probe.get("aiSelected"):
            logger.info("Douyin AI recommend cover already selected")
            return True
        try:
            result = page.evaluate(_SELECT_DOUYIN_AI_COVER_JS) or {}
            reason = result.get("reason", "")
            if result.get("ok"):
                human_pause(page, "after_click")
                _confirm_douyin_cover_modal(page, timeout_ms=2500)
                probe_after = _probe_douyin_ai_covers(page)
                if probe_after.get("aiSelected") or reason == "ai-already-selected":
                    logger.info("Douyin AI recommend cover: {}", reason)
                    return True
                logger.debug("Douyin AI cover click did not stick: {}", reason)
            else:
                logger.debug("Douyin AI cover select probe: {}", reason)
        except Exception as exc:
            logger.debug("Douyin AI cover select probe failed: {}", exc)

        cover = _locate_ai_recommend_cover(page)
        if cover is not None:
            try:
                cover.scroll_into_view_if_needed(timeout=3000)
                human_click_element(page, cover, timeout_ms=3000)
                human_pause(page, "after_click")
                _confirm_douyin_cover_modal(page, timeout_ms=2500)
                probe_after = _probe_douyin_ai_covers(page)
                if probe_after.get("aiSelected"):
                    logger.info("Douyin AI recommend cover selected via locator fallback")
                    return True
            except Exception as exc:
                logger.debug("Douyin AI cover locator click failed: {}", exc)
        page.wait_for_timeout(1000)

    logger.warning("Douyin AI recommend cover skipped after {}ms", capped_ms)
    return False


def prepare_douyin_ai_cover(page: Page, *, timeout_ms: int) -> bool:
    """Open cover panel, wait for AI thumbnails, and select the AI recommend cover."""
    wait_ms = min(timeout_ms, DOUYIN_AI_COVER_WAIT_MAX_MS)
    select_ms = min(timeout_ms, DOUYIN_COVER_SELECT_MAX_MS)
    logger.info("Douyin AI cover: opening panel and waiting up to {}ms", wait_ms)
    ensure_douyin_cover_panel_visible(page)
    if not wait_for_douyin_ai_covers(page, timeout_ms=wait_ms):
        ensure_douyin_cover_panel_visible(page)
        if not wait_for_douyin_ai_covers(page, timeout_ms=min(wait_ms // 2, 45_000)):
            return False
    return select_douyin_ai_recommend_cover(page, timeout_ms=select_ms)


def _locate_douyin_title_field(page: Page) -> Locator | None:
    title_loc = _first_visible_locator(page, TITLE_SELECTORS)
    if title_loc is not None:
        return title_loc
    for placeholder in ("填写标题", "作品标题", "标题"):
        locator = page.get_by_placeholder(re.compile(re.escape(placeholder)))
        if locator.count() > 0:
            candidate = locator.first
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
    return None


def _scroll_form_field_into_view(locator: Locator, *, timeout_ms: int) -> None:
    locator.scroll_into_view_if_needed(timeout=min(timeout_ms, 10_000))
    try:
        locator.evaluate(
            """(el) => {
                el.scrollIntoView({ block: 'center', behavior: 'instant' });
            }"""
        )
    except Exception:
        pass


def fill_douyin_title(page: Page, title: str, *, timeout_ms: int, max_length: int = 55) -> bool:
    text = normalize_douyin_title(title, max_length=max_length)
    if not text:
        return False
    title_loc = _locate_douyin_title_field(page)
    if title_loc is None:
        logger.warning("Douyin title field not found")
        return False
    try:
        title_loc.wait_for(state="visible", timeout=timeout_ms)
        _scroll_form_field_into_view(title_loc, timeout_ms=timeout_ms)
        human_pause(page, "step")
        _set_field_text(page, title_loc, text)
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
        _scroll_form_field_into_view(desc_loc, timeout_ms=timeout_ms)
        human_pause(page, "step")
        _set_field_text(page, desc_loc, description)
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
        _set_field_text(page, topic_loc, topic_line)
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
        human_pause(page, "polling")
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


def declare_douyin_ai_generated(page: Page, *, timeout_ms: int = 8_000) -> bool:
    """Click 自主声明 → 内容由AI生成. Not wired into publish yet (deferred)."""
    try:
        opener = page.get_by_text("自主声明", exact=False)
        if opener.count() == 0:
            logger.warning("Douyin AI declaration control not found")
            return False
        human_click_element(page, opener.first, timeout_ms=min(timeout_ms, 4000))
        human_pause(page, "modal")

        option = None
        for text in ("内容由AI生成", "内容由 AI 生成"):
            candidate = page.get_by_text(text, exact=False)
            if candidate.count() == 0:
                continue
            try:
                if candidate.first.is_visible(timeout=min(timeout_ms, 3000)):
                    option = candidate.first
                    break
            except Exception:
                continue
        if option is None:
            logger.warning("Douyin AI generated option not found after opening 自主声明")
            return False
        human_click_element(page, option, timeout_ms=min(timeout_ms, 4000))

        for text in ("确定", "完成", "保存"):
            confirm = page.get_by_text(text, exact=True)
            if confirm.count() == 0:
                continue
            try:
                if confirm.first.is_visible(timeout=1500):
                    human_click_element(page, confirm.first, timeout_ms=3000)
                    break
            except Exception:
                continue
        logger.info("Douyin AI generated declaration selected")
        return True
    except Exception as exc:
        logger.warning("Douyin AI declaration failed: %s", exc)
        return False


def click_douyin_publish(page: Page, *, timeout_ms: int) -> bool:
    from services.publishing.adapters.publish_button_helpers import (
        click_publish_button,
        confirm_publish_dialogs,
        scroll_to_publish_area,
        wait_for_publish_success,
    )

    capped_ms = min(timeout_ms, DOUYIN_PUBLISH_MAX_MS)
    human_pause(page, "before_publish")
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
    human_pause(page, "modal")
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
