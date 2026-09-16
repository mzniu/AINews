"""Human-like mouse/keyboard interactions and light browser stealth for publishing."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from loguru import logger

from services.publishing.human_pacing import human_pause

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Locator, Page, Playwright

STEALTH_CHROMIUM_ARGS = (
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
)

STEALTH_INIT_SCRIPT = """
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  try {
    window.chrome = window.chrome || { runtime: {} };
  } catch (e) {}
  try {
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
      parameters && parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
    );
  } catch (e) {}
})();
"""

DEFAULT_PUBLISH_VIEWPORT = {"width": 1440, "height": 900}
DEFAULT_PUBLISH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def launch_publish_browser(playwright: Playwright, *, headless: bool = False) -> Browser:
    return playwright.chromium.launch(
        headless=headless,
        args=list(STEALTH_CHROMIUM_ARGS),
    )


def create_publish_browser_context(
    browser: Browser,
    *,
    storage_state: str | None = None,
    account_id: str | None = None,
) -> BrowserContext:
    from services.publishing.fingerprint_probe import resolve_user_agent
    from services.publishing.fingerprint_shim import build_combined_stealth_init_script
    from services.publishing.persona import load_persona

    persona = load_persona(account_id) if account_id else {}
    context = browser.new_context(
        storage_state=storage_state,
        viewport=DEFAULT_PUBLISH_VIEWPORT,
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        user_agent=resolve_user_agent(account_id=account_id),
        color_scheme="light",
    )
    context.add_init_script(build_combined_stealth_init_script(persona))
    return context


def open_stealth_browser(
    playwright: Playwright,
    *,
    headless: bool = False,
    storage_state: str | None = None,
    account_id: str | None = None,
) -> tuple[Browser, BrowserContext]:
    """Launch Chromium with anti-automation flags and a normalized publish context."""
    browser = launch_publish_browser(playwright, headless=headless)
    context = create_publish_browser_context(
        browser,
        storage_state=storage_state,
        account_id=account_id,
    )
    return browser, context


def human_idle_on_page(page: Page, *, moves: int | None = None) -> None:
    """Small random mouse moves / scroll to mimic reading the page."""
    viewport = page.viewport_size or DEFAULT_PUBLISH_VIEWPORT
    count = moves if moves is not None else random.randint(1, 3)
    for _ in range(count):
        x = random.randint(80, max(120, viewport["width"] - 80))
        y = random.randint(80, max(120, viewport["height"] - 80))
        try:
            page.mouse.move(x, y, steps=random.randint(10, 24))
        except Exception:
            pass
        page.wait_for_timeout(random.randint(180, 520))
    if random.random() < 0.7:
        delta = random.randint(60, 220) * random.choice((1, -1))
        try:
            page.mouse.wheel(0, delta)
        except Exception:
            pass
        page.wait_for_timeout(random.randint(250, 700))


def human_click(page: Page, locator: Locator, *, timeout_ms: int = 8_000) -> None:
    """Move mouse to element and click at a slightly random point."""
    locator.wait_for(state="visible", timeout=timeout_ms)
    locator.scroll_into_view_if_needed(timeout=timeout_ms)
    box = locator.bounding_box()
    if box is None:
        locator.click(timeout=timeout_ms, delay=random.randint(40, 140))
        human_pause(page, "after_click")
        return

    width = max(box["width"], 4.0)
    height = max(box["height"], 4.0)
    margin_x = min(8.0, width * 0.2)
    margin_y = min(8.0, height * 0.2)
    x = box["x"] + margin_x + random.random() * max(width - 2 * margin_x, 1.0)
    y = box["y"] + margin_y + random.random() * max(height - 2 * margin_y, 1.0)

    start_x = max(0.0, x - random.randint(40, 140))
    start_y = max(0.0, y - random.randint(20, 80))
    page.mouse.move(start_x, start_y, steps=random.randint(8, 18))
    page.wait_for_timeout(random.randint(80, 220))
    page.mouse.move(x, y, steps=random.randint(4, 12))
    page.wait_for_timeout(random.randint(60, 180))
    page.mouse.click(x, y, delay=random.randint(50, 160))
    human_pause(page, "after_click")


def clear_input_field(page: Page) -> None:
    """Clear the focused editable field without selecting the whole page."""
    page.evaluate(
        """() => {
            const el = document.activeElement;
            if (!el || el === document.body) return;
            const tag = (el.tagName || '').toUpperCase();
            if (tag === 'INPUT' || tag === 'TEXTAREA') {
                el.select();
                return;
            }
            if (el.isContentEditable) {
                const range = document.createRange();
                range.selectNodeContents(el);
                const sel = window.getSelection();
                if (sel) {
                    sel.removeAllRanges();
                    sel.addRange(range);
                }
            }
        }"""
    )
    page.wait_for_timeout(random.randint(60, 160))
    page.keyboard.press("Backspace")
    page.wait_for_timeout(random.randint(80, 180))


def _clear_locator_field(page: Page, locator: Locator) -> None:
    """Select and clear text inside a specific field (avoids page-wide Ctrl+A)."""
    locator.evaluate(
        """(el) => {
            el.focus();
            const tag = (el.tagName || '').toUpperCase();
            if (tag === 'INPUT' || tag === 'TEXTAREA') {
                el.select();
                return;
            }
            if (el.isContentEditable) {
                const range = document.createRange();
                range.selectNodeContents(el);
                const sel = window.getSelection();
                if (sel) {
                    sel.removeAllRanges();
                    sel.addRange(range);
                }
            }
        }"""
    )
    page.wait_for_timeout(random.randint(60, 160))
    page.keyboard.press("Backspace")
    page.wait_for_timeout(random.randint(80, 180))


def human_type_text(
    page: Page,
    locator: Locator,
    text: str,
    *,
    clear_first: bool = True,
    timeout_ms: int = 8_000,
) -> None:
    """Type text with per-character delays instead of fill()/DOM injection."""
    if not text:
        return
    from services.publishing.persona import get_persona_typing_delay_scale

    typing_scale = max(0.5, get_persona_typing_delay_scale())
    human_pause(page, "before_type")
    human_click(page, locator, timeout_ms=timeout_ms)
    if clear_first:
        _clear_locator_field(page, locator)

    lines = text.split("\n")
    for line_index, line in enumerate(lines):
        for char in line:
            delay = int(random.randint(45, 190) * typing_scale)
            if char == " " and random.random() < 0.12:
                page.wait_for_timeout(random.randint(120, 350))
            page.keyboard.type(char, delay=delay)
            if random.random() < 0.06:
                page.wait_for_timeout(random.randint(150, 450))
        if line_index < len(lines) - 1:
            page.keyboard.press("Enter")
            page.wait_for_timeout(random.randint(200, 500))
    human_pause(page, "after_type")


def human_click_publish_target(page: Page, locator: Locator, *, timeout_ms: int = 8_000) -> bool:
    """Click a publish control with extra hesitation before submitting."""
    try:
        if not locator.is_visible(timeout=min(timeout_ms, 3000)):
            return False
        human_pause(page, "before_publish")
        human_click(page, locator, timeout_ms=timeout_ms)
        return True
    except Exception as exc:
        logger.debug("Human publish click failed: {}", exc)
        return False
