"""Title-generation prompt config: base YAML + local overrides."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

PROMPTS_BASE_PATH = Config.ROOT_DIR / "config" / "content_prompts.yaml"
PROMPTS_LOCAL_PATH = Config.ROOT_DIR / "config" / "content_prompts.local.yaml"

TITLE_PROMPT_KEYS = (
    "system_role",
    "content_formula",
    "main_line1_patterns",
    "short_title_patterns",
    "stage2_main_line1",
    "stage2_short_title",
    "json_main_line1_hint",
    "json_short_title_hint",
    "first_comment_patterns",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_merged_content_prompts() -> dict[str, Any]:
    base = _load_yaml(PROMPTS_BASE_PATH)
    local = _load_yaml(PROMPTS_LOCAL_PATH)
    if not local:
        return base
    return _deep_merge(base, local)


def get_title_prompts() -> dict[str, str]:
    title = (load_merged_content_prompts().get("title") or {})
    return {key: str(title.get(key) or "").strip() for key in TITLE_PROMPT_KEYS}


def get_system_role() -> str:
    return get_title_prompts()["system_role"]


def json_main_line1_hint() -> str:
    return get_title_prompts()["json_main_line1_hint"]


def json_short_title_hint() -> str:
    return get_title_prompts()["json_short_title_hint"]


def get_title_prompt_settings() -> dict[str, Any]:
    prompts = get_title_prompts()
    return {
        **prompts,
        "keys": list(TITLE_PROMPT_KEYS),
        "local_config_path": str(PROMPTS_LOCAL_PATH),
        "has_local_override": PROMPTS_LOCAL_PATH.exists(),
    }


def save_title_prompts(updates: dict[str, Any]) -> dict[str, str]:
    allowed = {key: str(updates[key]).strip() for key in TITLE_PROMPT_KEYS if key in updates}
    if not allowed:
        raise ValueError("没有可保存的标题提示词字段")
    for key, value in allowed.items():
        if key != "first_comment_patterns" and not value:
            raise ValueError(f"{key} 不能为空")
    local = _load_yaml(PROMPTS_LOCAL_PATH)
    title = local.setdefault("title", {})
    title.update(allowed)
    local["title"] = title
    PROMPTS_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPTS_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return get_title_prompts()


def reset_title_prompts() -> dict[str, str]:
    if PROMPTS_LOCAL_PATH.exists():
        local = _load_yaml(PROMPTS_LOCAL_PATH)
        local.pop("title", None)
        if local:
            with open(PROMPTS_LOCAL_PATH, "w", encoding="utf-8") as handle:
                yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
        else:
            PROMPTS_LOCAL_PATH.unlink()
    return get_title_prompts()
