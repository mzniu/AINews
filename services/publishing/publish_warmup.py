"""Pre-upload warmup behavior for creator center sessions."""
from __future__ import annotations

import random
from typing import Any

from loguru import logger

from services.publishing.human_interaction import DEFAULT_PUBLISH_VIEWPORT, human_idle_on_page
from services.publishing.human_pacing import human_pause
from services.publishing.persona import get_persona_warmup_moves
from services.publishing.registry import load_publishing_yaml


def load_publish_warmup_config(yaml: dict[str, Any] | None = None) -> dict[str, Any]:
    data = yaml or load_publishing_yaml()
    defaults = data.get("defaults") or {}
    cfg = defaults.get("publish_warmup") or {}
    idle_moves = cfg.get("idle_moves") or [2, 4]
    if not isinstance(idle_moves, (list, tuple)) or len(idle_moves) < 2:
        idle_moves = [2, 4]
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "idle_moves": [int(idle_moves[0]), int(idle_moves[1])],
        "browse_home_first": bool(cfg.get("browse_home_first", True)),
    }


def warmup_creator_session(page, *, platform_id: str = "") -> None:
    """Idle on the creator page before upload to mimic browsing."""
    cfg = load_publish_warmup_config()
    if not cfg.get("enabled", True):
        human_pause(page, "page_load")
        return

    low, high = cfg["idle_moves"]
    moves = get_persona_warmup_moves((low, high))
    logger.debug("Publish warmup platform={} idle_moves={}", platform_id or "unknown", moves)
    human_idle_on_page(page, moves=moves)
    human_pause(page, "page_load")

    if random.random() < 0.65:
        viewport = page.viewport_size or DEFAULT_PUBLISH_VIEWPORT
        height = max(viewport.get("height", 900), 400)
        for ratio in (0.3, 0.6):
            try:
                page.mouse.wheel(0, int(height * ratio * random.uniform(0.15, 0.35)))
            except Exception:
                pass
            page.wait_for_timeout(random.randint(200, 500))
