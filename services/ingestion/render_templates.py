"""Render templates: builtin YAML + local overrides."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

RENDER_TEMPLATES_BASE_PATH = Config.ROOT_DIR / "config" / "render_templates.yaml"
RENDER_TEMPLATES_LOCAL_PATH = Config.ROOT_DIR / "config" / "render_templates.local.yaml"

KNOWN_LAYOUT_KINDS = frozenset({"classic_overlay", "chronicle_frame"})


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _index_templates(items: Any) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        return indexed
    for item in items:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or "").strip()
        if tid:
            indexed[tid] = copy.deepcopy(item)
    return indexed


def load_merged_render_templates() -> dict[str, Any]:
    base = _load_yaml(RENDER_TEMPLATES_BASE_PATH)
    local = _load_yaml(RENDER_TEMPLATES_LOCAL_PATH)
    templates = _index_templates(base.get("templates"))
    local_templates = _index_templates(local.get("templates"))
    order = [str(item.get("id")) for item in (base.get("templates") or []) if isinstance(item, dict) and item.get("id")]
    for tid, patch in local_templates.items():
        if tid in templates:
            templates[tid] = _deep_merge(templates[tid], patch)
        else:
            templates[tid] = patch
            order.append(tid)
    default_id = str(
        local.get("default_template_id") or base.get("default_template_id") or "flash_news_portrait"
    )
    return {
        "version": int(local.get("version") or base.get("version") or 1),
        "default_template_id": default_id,
        "templates": [templates[tid] for tid in order if tid in templates],
    }


def list_render_templates() -> dict[str, Any]:
    merged = load_merged_render_templates()
    return {
        "default_template_id": merged["default_template_id"],
        "templates": copy.deepcopy(merged["templates"]),
    }


def get_default_template_id() -> str:
    return str(load_merged_render_templates()["default_template_id"])


def _require_layout_kind(template: dict[str, Any]) -> None:
    kind = str(template.get("layout_kind") or "").strip()
    if kind not in KNOWN_LAYOUT_KINDS:
        raise ValueError(f"unknown_layout_kind: {kind or '(empty)'}")


def get_render_template(template_id: str | None) -> dict[str, Any]:
    merged = load_merged_render_templates()
    wanted = str(template_id or "").strip() or str(merged["default_template_id"])
    for item in merged["templates"]:
        if str(item.get("id")) == wanted:
            _require_layout_kind(item)
            return copy.deepcopy(item)
    raise ValueError(f"unknown_render_template: {wanted}")


def _write_local(data: dict[str, Any]) -> None:
    RENDER_TEMPLATES_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RENDER_TEMPLATES_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle, allow_unicode=True, sort_keys=False)


def set_default_template_id(template_id: str) -> dict[str, Any]:
    get_render_template(template_id)
    local = _load_yaml(RENDER_TEMPLATES_LOCAL_PATH)
    local["default_template_id"] = str(template_id).strip()
    _write_local(local)
    return list_render_templates()


def save_render_template(template_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    current = get_render_template(template_id)
    merged = _deep_merge(current, patch or {})
    merged["id"] = template_id
    if current.get("builtin"):
        merged["builtin"] = True
    _require_layout_kind(merged)
    local = _load_yaml(RENDER_TEMPLATES_LOCAL_PATH)
    items = list(local.get("templates") or [])
    found = False
    for index, item in enumerate(items):
        if str(item.get("id")) == template_id:
            items[index] = _deep_merge(item, patch or {})
            items[index]["id"] = template_id
            found = True
            break
    if not found:
        items.append({"id": template_id, **(patch or {})})
    local["templates"] = items
    _write_local(local)
    return get_render_template(template_id)


def duplicate_render_template(
    template_id: str,
    *,
    new_id: str,
    label: str | None = None,
) -> dict[str, Any]:
    source = get_render_template(template_id)
    tid = str(new_id or "").strip()
    if not tid:
        raise ValueError("new_id is required")
    try:
        get_render_template(tid)
    except ValueError:
        pass
    else:
        raise ValueError(f"render_template_exists: {tid}")
    clone = copy.deepcopy(source)
    clone["id"] = tid
    clone["builtin"] = False
    clone["label"] = label or f"{source.get('label') or tid} 副本"
    local = _load_yaml(RENDER_TEMPLATES_LOCAL_PATH)
    items = list(local.get("templates") or [])
    items.append(clone)
    local["templates"] = items
    _write_local(local)
    return get_render_template(tid)


def delete_render_template(template_id: str) -> dict[str, Any]:
    spec = get_render_template(template_id)
    if spec.get("builtin"):
        raise ValueError("cannot delete builtin render template")
    local = _load_yaml(RENDER_TEMPLATES_LOCAL_PATH)
    items = [item for item in (local.get("templates") or []) if str(item.get("id")) != template_id]
    local["templates"] = items
    if str(local.get("default_template_id")) == template_id:
        local["default_template_id"] = "flash_news_portrait"
    _write_local(local)
    return list_render_templates()
