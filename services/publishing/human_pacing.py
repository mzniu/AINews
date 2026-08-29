"""Human-like delays between Playwright publish actions."""
from __future__ import annotations

import os
import random
import time
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from loguru import logger

from services.publishing.registry import load_publishing_yaml

if TYPE_CHECKING:
    from playwright.sync_api import Page

PublishPauseKind = Literal[
    "page_load",
    "step",
    "after_upload",
    "after_click",
    "before_type",
    "after_type",
    "before_publish",
    "polling",
    "modal",
]

_PAUSE_RANGES_MS: dict[PublishPauseKind, tuple[int, int]] = {
    "page_load": (3000, 5500),
    "step": (2500, 5000),
    "after_upload": (4000, 7500),
    "after_click": (1200, 2400),
    "before_type": (900, 2000),
    "after_type": (1500, 3200),
    "before_publish": (3000, 6000),
    "polling": (2200, 3800),
    "modal": (1500, 3000),
}


@lru_cache(maxsize=1)
def _pacing_settings() -> tuple[bool, float]:
    data = load_publishing_yaml()
    defaults = data.get("defaults") or {}
    pacing = defaults.get("human_pacing") or {}
    enabled = pacing.get("enabled", True)
    multiplier = float(pacing.get("multiplier", 1.0))
    env_multiplier = os.getenv("PUBLISH_HUMAN_PACING_MULTIPLIER", "").strip()
    if env_multiplier:
        try:
            multiplier = float(env_multiplier)
        except ValueError:
            logger.warning("Invalid PUBLISH_HUMAN_PACING_MULTIPLIER: {}", env_multiplier)
    env_enabled = os.getenv("PUBLISH_HUMAN_PACING_ENABLED", "").strip().lower()
    if env_enabled in {"0", "false", "no", "off"}:
        enabled = False
    elif env_enabled in {"1", "true", "yes", "on"}:
        enabled = True
    return enabled, max(0.25, multiplier)


def is_human_pacing_enabled() -> bool:
    return _pacing_settings()[0]


def get_human_pacing_multiplier() -> float:
    return _pacing_settings()[1]


def _sleep_ms(page: Page | None, ms: int) -> None:
    if ms <= 0:
        return
    if page is not None:
        page.wait_for_timeout(ms)
    else:
        time.sleep(ms / 1000)


def human_pause(page: Page | None, kind: PublishPauseKind = "step") -> None:
    """Pause for a human-like duration for a specific interaction type."""
    enabled, multiplier = _pacing_settings()
    low, high = _PAUSE_RANGES_MS[kind]
    if not enabled:
        _sleep_ms(page, low)
        return
    from services.publishing.persona import get_persona_pause_multiplier

    persona_mult = max(0.5, get_persona_pause_multiplier())
    ms = int(random.uniform(low, high) * multiplier * persona_mult)
    _sleep_ms(page, ms)


def human_wait(page: Page, minimum_ms: int) -> None:
    """Wait at least minimum_ms with jitter; used as a drop-in for fixed timeouts."""
    enabled, multiplier = _pacing_settings()
    if not enabled:
        _sleep_ms(page, minimum_ms)
        return
    from services.publishing.persona import get_persona_pause_multiplier

    persona_mult = max(0.5, get_persona_pause_multiplier())
    base = int(max(minimum_ms, 400) * multiplier * persona_mult)
    jitter = random.randint(200, 900) if minimum_ms >= 1000 else random.randint(120, 450)
    _sleep_ms(page, base + jitter)


def pause_publish_step(page: Page, step: str = "") -> None:
    """Pause between major publish workflow steps (upload → cover → title → publish)."""
    if step:
        logger.debug("Publish human pacing before step: {}", step)
    human_pause(page, "step")
