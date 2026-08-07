"""Helpers for filling Kuaishou creator center publish form."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

FILE_INPUT_SELECTORS = (
    'input[type="file"][accept*="video"]',
    'input[type="file"][accept*="mp4"]',
    'input[type="file"]',
)

UPLOAD_TRIGGER_TEXTS = ("上传视频", "点击上传", "去上传", "拖拽视频")

UPLOAD_ADVANCE_TEXTS = (
    "下一步",
    "继续编辑",
    "去编辑",
    "完成编辑",
    "进入编辑",
    "确定",
    "完成",
)

GUIDE_TOOLTIP_SKIP_SELECTORS = (
    '[role="alertdialog"] [data-action="skip"]',
    '[aria-modal="true"] [data-action="skip"]',
    '[role="alertdialog"] [aria-label="Skip"]',
    'div[role="button"][aria-label="Skip"]',
    'div[role="button"][title="Skip"]',
)

GUIDE_TOOLTIP_HINT_PATTERN = re.compile(r"作品信息|便捷填写作品关键信息", re.I)

FILE_INPUT_SCOPED_SELECTORS = (
    'div[class*="upload"] input[type="file"]',
    'div[class*="Upload"] input[type="file"]',
    'div[class*="publish"] input[type="file"]',
)

TITLE_SELECTORS = (
    'textarea[placeholder*="填写标题"]',
    'input[placeholder*="填写标题"]',
    'textarea[placeholder*="标题"]',
    'input[placeholder*="标题"]',
)

DESCRIPTION_SELECTORS = (
    "#work-description-edit",
    'div[id="work-description-edit"]',
    'div[class*="edit-desc"] div[contenteditable="true"]',
    'div[class*="caption"] div[contenteditable="true"]',
    'textarea[placeholder*="话题和描述"]',
    'textarea[placeholder*="作品描述"]',
    'textarea[placeholder*="描述"]',
    'div[contenteditable="true"][placeholder*="作品描述"]',
    'div[contenteditable="true"][data-placeholder*="描述"]',
)

UPLOAD_READY_PATTERN = re.compile(r"上传成功|上传完成|解析完成|转码完成", re.I)
UPLOADING_PATTERN = re.compile(r"上传中|正在上传|解析中|处理中|转码", re.I)
HASHTAG_PATTERN = re.compile(r"#([^\s#]+)")
DEFAULT_MAX_TAGS = 4


def normalize_kuaishou_title(title: str, *, max_length: int = 50) -> str:
    text = (title or "").strip()
    if len(text) > max_length:
        return text[:max_length]
    return text


def normalize_kuaishou_tags(tags: list[str], *, max_tags: int = DEFAULT_MAX_TAGS) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in tags:
        token = str(raw).strip().lstrip("#")
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
        if len(normalized) >= max_tags:
            break
    return normalized


def format_kuaishou_tags(tags: list[str], *, max_tags: int = DEFAULT_MAX_TAGS) -> str:
    parts: list[str] = []
    for tag in normalize_kuaishou_tags(tags, max_tags=max_tags):
        parts.append(f"#{tag}")
    return " ".join(parts)


def compose_kuaishou_description(
    description: str,
    tags: list[str],
    *,
    max_tags: int = DEFAULT_MAX_TAGS,
) -> str:
    body = (description or "").strip()
    embedded_tags = HASHTAG_PATTERN.findall(body)
    body = HASHTAG_PATTERN.sub("", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    merged_tags = normalize_kuaishou_tags([*embedded_tags, *tags], max_tags=max_tags)
    tags_line = format_kuaishou_tags(merged_tags, max_tags=max_tags)
    if tags_line and body:
        return f"{body}\n{tags_line}"
    if tags_line:
        return tags_line
    return body


def _set_contenteditable_text(locator: Locator, text: str) -> None:
    locator.evaluate(
        """(el, value) => {
            el.focus();
            const lines = String(value || '').split('\\n');
            const html = lines
                .map((line) => `<div>${line.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>`)
                .join('');
            el.innerHTML = html || '<div><br></div>';
            el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        text,
    )


def _locate_kuaishou_description_editor(page: Page) -> Locator | None:
    for selector in DESCRIPTION_SELECTORS:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(min(count, 4)):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
    try:
        label = page.get_by_text("作品描述", exact=True).first
        if label.is_visible(timeout=1500):
            container = label.locator("xpath=ancestor::div[contains(@class,'caption')][1]")
            editor = container.locator('[contenteditable="true"]').first
            if editor.is_visible(timeout=1500):
                return editor
    except Exception:
        pass
    return None


def _description_has_text(locator: Locator) -> bool:
    try:
        return bool(
            locator.evaluate(
                "(el) => Boolean((el.innerText || el.textContent || '').trim())"
            )
        )
    except Exception:
        return False


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
    _set_contenteditable_text(locator, text)


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


def _locate_kuaishou_file_input(page: Page) -> Locator | None:
    for selector in FILE_INPUT_SCOPED_SELECTORS + FILE_INPUT_SELECTORS:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(min(count, 6)):
            candidate = locator.nth(index)
            try:
                if candidate.count() > 0:
                    return candidate
            except Exception:
                continue
    return None


def _is_kuaishou_editor_visible(page: Page) -> bool:
    return (
        _first_visible_locator(page, TITLE_SELECTORS) is not None
        or _locate_kuaishou_description_editor(page) is not None
    )


def _is_kuaishou_guide_tooltip_visible(page: Page) -> bool:
    for selector in GUIDE_TOOLTIP_SKIP_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=300):
                return True
        except Exception:
            continue
    try:
        if page.locator('[role="alertdialog"][aria-modal="true"]').first.is_visible(timeout=300):
            return True
    except Exception:
        pass
    try:
        if page.get_by_text(GUIDE_TOOLTIP_HINT_PATTERN).first.is_visible(timeout=300):
            return True
    except Exception:
        pass
    return False


def dismiss_kuaishou_guide_tooltips(page: Page, *, max_rounds: int = 4) -> bool:
    """Close the 1/4 onboarding tooltip (Skip) that blocks the publish form."""
    dismissed = False
    for _ in range(max_rounds):
        if not _is_kuaishou_guide_tooltip_visible(page):
            break
        closed = False
        for selector in GUIDE_TOOLTIP_SKIP_SELECTORS:
            try:
                skip = page.locator(selector).first
                if skip.is_visible(timeout=500):
                    skip.click(timeout=3000)
                    page.wait_for_timeout(500)
                    logger.info("Kuaishou onboarding tooltip dismissed via %s", selector)
                    closed = True
                    dismissed = True
                    break
            except Exception:
                continue
        if not closed:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                if not _is_kuaishou_guide_tooltip_visible(page):
                    dismissed = True
            except Exception:
                pass
            break
    return dismissed or not _is_kuaishou_guide_tooltip_visible(page)


def ensure_upload_surface(page: Page, *, timeout_ms: int) -> bool:
    if _locate_kuaishou_file_input(page) is not None:
        return True
    try:
        page.wait_for_selector('input[type="file"]', state="attached", timeout=timeout_ms)
        return True
    except Exception:
        pass
    for text in UPLOAD_TRIGGER_TEXTS:
        try:
            trigger = page.get_by_text(text, exact=False).first
            if trigger.is_visible(timeout=1500):
                return True
        except Exception:
            continue
    return False


def _click_upload_trigger_with_file_chooser(
    page: Page,
    video_path: str,
    *,
    timeout_ms: int,
) -> bool:
    for text in UPLOAD_TRIGGER_TEXTS:
        try:
            trigger = page.get_by_text(text, exact=False).first
            if not trigger.is_visible(timeout=1500):
                continue
            with page.expect_file_chooser(timeout=min(timeout_ms, 15_000)) as chooser_info:
                trigger.click(timeout=5000)
            chooser_info.value.set_files(video_path)
            page.wait_for_timeout(2000)
            logger.info("Kuaishou video set via file chooser (%s)", text)
            return True
        except Exception as exc:
            logger.debug("Kuaishou file chooser via %r failed: %s", text, exc)
            continue
    return False


def upload_kuaishou_video(page: Page, video_path: str, *, timeout_ms: int) -> bool:
    if not ensure_upload_surface(page, timeout_ms=min(timeout_ms, 30_000)):
        logger.warning("Kuaishou upload surface not found")
        return False

    file_input = _locate_kuaishou_file_input(page)
    if file_input is not None:
        try:
            file_input.set_input_files(video_path, timeout=timeout_ms)
            page.wait_for_timeout(2000)
            logger.info("Kuaishou video set via hidden file input")
            return True
        except Exception as exc:
            logger.warning("Kuaishou direct file input upload failed: %s", exc)

    if _click_upload_trigger_with_file_chooser(page, video_path, timeout_ms=timeout_ms):
        return True

    try:
        fallback = page.locator('input[type="file"]').first
        fallback.set_input_files(video_path, timeout=timeout_ms)
        page.wait_for_timeout(2000)
        logger.info("Kuaishou video set via fallback file input")
        return True
    except Exception as exc:
        logger.warning("Kuaishou video upload failed: %s", exc)
        return False


def _click_kuaishou_advance_buttons(page: Page) -> bool:
    if _is_kuaishou_guide_tooltip_visible(page):
        if dismiss_kuaishou_guide_tooltips(page):
            return True
    clicked = False
    for label in UPLOAD_ADVANCE_TEXTS:
        try:
            btn = page.get_by_role("button", name=re.compile(re.escape(label))).first
            if btn.is_visible(timeout=500):
                btn.click(timeout=3000)
                page.wait_for_timeout(1200)
                clicked = True
                break
        except Exception:
            continue
    if clicked:
        return True
    for label in ("下一步", "继续编辑", "去编辑", "完成编辑"):
        try:
            link = page.get_by_text(label, exact=True).first
            if link.is_visible(timeout=500):
                link.click(timeout=3000)
                page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    return False


def advance_past_kuaishou_upload_window(page: Page, *, timeout_ms: int) -> bool:
    """Leave the upload-only modal/surface and reach the metadata editor."""
    dismiss_kuaishou_guide_tooltips(page)
    if _is_kuaishou_editor_visible(page):
        return True

    deadline_attempts = max(3, timeout_ms // 3000)
    for _ in range(deadline_attempts):
        dismiss_kuaishou_guide_tooltips(page)
        if _is_kuaishou_editor_visible(page):
            return True

        try:
            if page.get_by_text(UPLOADING_PATTERN).first.is_visible(timeout=500):
                page.wait_for_timeout(2000)
                continue
        except Exception:
            pass

        if _click_kuaishou_advance_buttons(page):
            if _is_kuaishou_editor_visible(page):
                return True

        page.wait_for_timeout(2000)

    return _is_kuaishou_editor_visible(page)


def wait_for_kuaishou_video_ready(page: Page, *, timeout_ms: int) -> bool:
    deadline_attempts = max(5, timeout_ms // 3000)
    for _ in range(deadline_attempts):
        if _is_kuaishou_editor_visible(page):
            return True
        try:
            if page.get_by_text(UPLOAD_READY_PATTERN).first.is_visible(timeout=1000):
                if advance_past_kuaishou_upload_window(page, timeout_ms=min(timeout_ms, 30_000)):
                    return True
        except Exception:
            pass
        try:
            preview = page.locator('[class*="video-preview"], [class*="preview"]').first
            if preview.count() > 0 and preview.is_visible(timeout=1000):
                uploading = page.get_by_text(UPLOADING_PATTERN)
                if uploading.count() == 0 or not uploading.first.is_visible(timeout=500):
                    if advance_past_kuaishou_upload_window(page, timeout_ms=min(timeout_ms, 30_000)):
                        return True
        except Exception:
            pass
        if advance_past_kuaishou_upload_window(page, timeout_ms=5000):
            return True
        page.wait_for_timeout(2000)
    return _is_kuaishou_editor_visible(page)


def wait_for_kuaishou_editor(page: Page, *, timeout_ms: int) -> bool:
    deadline_attempts = max(3, timeout_ms // 5000)
    for _ in range(deadline_attempts):
        dismiss_kuaishou_guide_tooltips(page)
        if advance_past_kuaishou_upload_window(page, timeout_ms=5000):
            return True
        page.wait_for_timeout(2000)
    dismiss_kuaishou_guide_tooltips(page)
    return _is_kuaishou_editor_visible(page)


def fill_kuaishou_title(page: Page, title: str, *, timeout_ms: int, max_length: int = 50) -> bool:
    dismiss_kuaishou_guide_tooltips(page)
    text = normalize_kuaishou_title(title, max_length=max_length)
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
        logger.warning(f"Fill Kuaishou title failed: {exc}")
        return False


def fill_kuaishou_description(page: Page, description: str, *, timeout_ms: int) -> bool:
    dismiss_kuaishou_guide_tooltips(page)
    if not description:
        return False
    desc_loc = _locate_kuaishou_description_editor(page)
    if desc_loc is None:
        for placeholder in ("作品描述", "话题和描述", "描述", "说点什么"):
            locator = page.get_by_placeholder(re.compile(re.escape(placeholder)))
            if locator.count() > 0:
                desc_loc = locator.first
                break
    if desc_loc is None:
        logger.warning("Kuaishou description editor not found")
        return False
    try:
        desc_loc.wait_for(state="visible", timeout=timeout_ms)
        desc_loc.scroll_into_view_if_needed(timeout=5000)
        desc_loc.click(timeout=5000)
        tag_name = desc_loc.evaluate("(el) => el.tagName")
        if tag_name in {"TEXTAREA", "INPUT"}:
            desc_loc.fill("")
            desc_loc.press_sequentially(description, delay=15)
        else:
            _set_contenteditable_text(desc_loc, description)
            if not _description_has_text(desc_loc):
                desc_loc.click(timeout=3000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.insert_text(description)
        page.wait_for_timeout(500)
        if _description_has_text(desc_loc):
            return True
        logger.warning("Kuaishou description editor still empty after fill attempt")
        return False
    except Exception as exc:
        logger.warning(f"Fill Kuaishou description failed: {exc}")
        try:
            _set_field_text(desc_loc, description)
            return _description_has_text(desc_loc)
        except Exception as fallback_exc:
            logger.warning(f"Fill Kuaishou description fallback failed: {fallback_exc}")
            return False


KUAISHOU_PUBLISH_BUTTON_SELECTORS = (
    'button:has-text("发布")',
    'div[class*="publish"] button:has-text("发布")',
    '[class*="button-primary"]:has-text("发布")',
)


def click_kuaishou_publish(page: Page, *, timeout_ms: int) -> bool:
    from services.publishing.adapters.publish_button_helpers import click_publish_and_wait

    def _prepare(page: Page) -> None:
        dismiss_kuaishou_guide_tooltips(page)

    return click_publish_and_wait(
        page,
        timeout_ms=timeout_ms,
        button_texts=("发布",),
        extra_selectors=KUAISHOU_PUBLISH_BUTTON_SELECTORS,
        success_pattern=re.compile(r"发布成功|上传成功|作品已发布", re.I),
        success_url_hints=("cp.kuaishou.com/article/manage", "cp.kuaishou.com/profile"),
        before_click=_prepare,
    )
