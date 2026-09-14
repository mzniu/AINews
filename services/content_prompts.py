"""Title-generation prompt config: base YAML + local overrides."""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

PROMPTS_BASE_PATH = Config.ROOT_DIR / "config" / "content_prompts.yaml"
PROMPTS_LOCAL_PATH = Config.CONFIG_DIR / "content_prompts.local.yaml"

TITLE_PROMPT_KEYS = (
    "system_role",
    "content_formula",
    "main_line1_patterns",
    "short_title_patterns",
    "stage2_main_line1",
    "stage2_short_title",
    "summary_patterns",
    "stage2_summary",
    "json_main_line1_hint",
    "json_short_title_hint",
    "json_summary_hint",
    "first_comment_patterns",
)

OPTIONAL_EMPTY_PROMPT_KEYS = frozenset({"first_comment_patterns", "summary_patterns"})

_SUMMARY_LENGTH_RE = re.compile(r"(\d+)\s*[-~～]\s*(\d+)\s*字")


def _extract_summary_length_label(text: str) -> str | None:
    match = _SUMMARY_LENGTH_RE.search(text or "")
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}字"


def _default_json_summary_hint(length_label: str = "100-130字") -> str:
    return f"生成的摘要（{length_label}，以「小牛说：」开头，话题引入→关键事实→轻观点）"


def _canonical_summary_length(title: dict[str, Any]) -> str | None:
    stage2 = str(title.get("stage2_summary") or "")
    patterns = str(title.get("summary_patterns") or "")
    return _extract_summary_length_label(stage2) or _extract_summary_length_label(patterns)


def _sync_summary_json_hint(title: dict[str, Any]) -> None:
    """Keep json_summary_hint length aligned with stage2_summary / summary_patterns."""
    length = _canonical_summary_length(title)
    if not length:
        return
    hint = str(title.get("json_summary_hint") or "")
    if _extract_summary_length_label(hint) != length:
        title["json_summary_hint"] = _default_json_summary_hint(length)


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


def json_summary_hint() -> str:
    prompts = get_title_prompts()
    hint = prompts.get("json_summary_hint", "").strip()
    canonical = _canonical_summary_length(prompts)
    if canonical and _extract_summary_length_label(hint) != canonical:
        return _default_json_summary_hint(canonical)
    if hint:
        return hint
    return _default_json_summary_hint(canonical or "100-130字")


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
        if key not in OPTIONAL_EMPTY_PROMPT_KEYS and not value:
            raise ValueError(f"{key} 不能为空")
    local = _load_yaml(PROMPTS_LOCAL_PATH)
    title = local.setdefault("title", {})
    title.update(allowed)
    merged = _deep_merge(_load_yaml(PROMPTS_BASE_PATH), local)
    merged_title = merged.setdefault("title", {})
    _sync_summary_json_hint(merged_title)
    if merged_title.get("json_summary_hint"):
        title["json_summary_hint"] = merged_title["json_summary_hint"]
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
