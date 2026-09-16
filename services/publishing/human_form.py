"""Unified human-like form interactions for publish adapters."""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from services.publishing.human_interaction import (
    clear_input_field,
    human_click,
    human_type_text,
)
from services.publishing.human_pacing import human_pause

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


def human_fill(
    page: Page,
    locator: Locator,
    text: str,
    *,
    clear_first: bool = True,
    timeout_ms: int = 8_000,
) -> None:
    """Type into inputs or inject contenteditable text with human pacing."""
    if not text:
        return
    try:
        tag_name = locator.evaluate("(el) => el.tagName")
    except Exception:
        tag_name = ""
    if tag_name in {"TEXTAREA", "INPUT"}:
        human_type_text(page, locator, text, clear_first=clear_first, timeout_ms=timeout_ms)
        locator.evaluate(
            """(el) => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }"""
        )
        return
    human_fill_contenteditable(page, locator, text, timeout_ms=timeout_ms)


def human_fill_contenteditable(
    page: Page,
    locator: Locator,
    text: str,
    *,
    timeout_ms: int = 8_000,
) -> None:
    if not text:
        return
    human_click_element(page, locator, timeout_ms=timeout_ms)
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
    human_pause(page, "after_type")


def human_click_element(page: Page, locator: Locator, *, timeout_ms: int = 8_000) -> None:
    human_click(page, locator, timeout_ms=timeout_ms)


def human_clear_field(page: Page, locator: Locator, *, timeout_ms: int = 8_000) -> None:
    human_click_element(page, locator, timeout_ms=timeout_ms)
    clear_input_field(page)


def human_select_option(
    page: Page,
    locator: Locator,
    label: str,
    *,
    timeout_ms: int = 8_000,
) -> bool:
    if not label:
        return False
    try:
        human_click_element(page, locator, timeout_ms=timeout_ms)
        human_pause(page, "step")
        option = page.get_by_text(label, exact=False).first
        human_click_element(page, option, timeout_ms=timeout_ms)
        return True
    except Exception as exc:
        logger.debug("human_select_option failed for {}: {}", label, exc)
        return False


def human_upload_file(
    page: Page,
    locator: Locator,
    path: str,
    *,
    timeout_ms: int = 60_000,
) -> None:
    human_pause(page, "before_type")
    locator.set_input_files(path, timeout=timeout_ms)
    human_pause(page, "after_upload")
