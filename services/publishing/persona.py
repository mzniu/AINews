"""Per-account publish behavior persona (typing/pause/warmup variance)."""
from __future__ import annotations

import json
import random
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from src.utils.config import Config

_persona_account_id: ContextVar[str | None] = ContextVar("publish_persona_account_id", default=None)

DEFAULT_PERSONA: dict[str, Any] = {
    "typing_delay_scale": 1.0,
    "pause_multiplier": 1.0,
    "warmup_moves": 3,
    "languages": ["zh-CN", "zh", "en"],
    "hardware_concurrency": 8,
    "device_memory": 8,
}


def save_persona(account_id: str, persona: dict[str, Any]) -> None:
    path = persona_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**DEFAULT_PERSONA, **persona}
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def persona_path(account_id: str) -> Path:
    return Config.DATA_DIR / "publish" / "persona" / f"{account_id}.json"


def set_publish_persona_account(account_id: str | None) -> None:
    _persona_account_id.set(account_id)


def get_publish_persona_account() -> str | None:
    return _persona_account_id.get()


def load_persona(account_id: str) -> dict[str, Any]:
    path = persona_path(account_id)
    if not path.is_file():
        return dict(DEFAULT_PERSONA)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(DEFAULT_PERSONA)
        return {**DEFAULT_PERSONA, **data}
    except Exception:
        return dict(DEFAULT_PERSONA)


def ensure_persona_for_account(account_id: str) -> dict[str, Any]:
    path = persona_path(account_id)
    if path.is_file():
        return load_persona(account_id)
    persona = {
        "typing_delay_scale": round(random.uniform(0.85, 1.25), 2),
        "pause_multiplier": round(random.uniform(0.85, 1.2), 2),
        "warmup_moves": random.randint(2, 4),
    }
    save_persona(account_id, persona)
    return persona


def get_persona_pause_multiplier() -> float:
    account_id = get_publish_persona_account()
    if not account_id:
        return 1.0
    return float(load_persona(account_id).get("pause_multiplier", 1.0))


def get_persona_typing_delay_scale() -> float:
    account_id = get_publish_persona_account()
    if not account_id:
        return 1.0
    return float(load_persona(account_id).get("typing_delay_scale", 1.0))


def get_persona_warmup_moves(idle_range: tuple[int, int]) -> int:
    account_id = get_publish_persona_account()
    if account_id:
        persona = load_persona(account_id)
        if persona.get("warmup_moves") is not None:
            return int(persona["warmup_moves"])
    low, high = idle_range
    return random.randint(low, high)
