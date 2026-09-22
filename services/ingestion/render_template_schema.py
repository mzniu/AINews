"""Field catalog for the render-template settings editor."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from src.utils.config import Config

RENDER_TEMPLATE_SCHEMA_PATH = Config.ROOT_DIR / "config" / "render_template_schema.yaml"


@lru_cache(maxsize=1)
def load_render_template_schema() -> dict[str, Any]:
    with open(RENDER_TEMPLATE_SCHEMA_PATH, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("render_template_schema must be a mapping")
    groups = list(loaded.get("groups") or [])
    fields = list(loaded.get("fields") or [])
    if not groups or not fields:
        raise ValueError("render_template_schema needs groups and fields")
    return {"groups": groups, "fields": fields}


def schema_for_layout(layout_kind: str) -> dict[str, Any]:
    catalog = load_render_template_schema()
    kind = str(layout_kind or "").strip()
    fields: list[dict[str, Any]] = []
    used_groups: set[str] = set()
    for item in catalog["fields"]:
        if not isinstance(item, dict):
            continue
        kinds = item.get("layout_kinds")
        if kinds and kind not in {str(value) for value in kinds}:
            continue
        fields.append(item)
        group = str(item.get("group") or "").strip()
        if group:
            used_groups.add(group)
    groups = [
        group
        for group in catalog["groups"]
        if isinstance(group, dict) and str(group.get("id") or "") in used_groups
    ]
    return {"groups": groups, "fields": fields}


def _scalar_yaml(value: Any) -> str:
    dumped = yaml.dump(
        value,
        allow_unicode=True,
        default_flow_style=True,
        sort_keys=False,
    ).strip()
    if dumped.endswith("\n..."):
        dumped = dumped[: -len("\n...")]
    if dumped.endswith(" ..."):
        dumped = dumped[: -len(" ...")]
    if dumped.endswith("..."):
        dumped = dumped[:-3].rstrip()
    return dumped


def _comment_for(path: str, labels: dict[str, str]) -> str:
    label = labels.get(path)
    if not label:
        return ""
    return f"  # {label}"


def _emit(obj: Any, indent: int, prefix: str, lines: list[str], labels: dict[str, str]) -> None:
    pad = "  " * indent
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        key_text = str(key)
        comment = _comment_for(path, labels)
        if isinstance(value, dict):
            lines.append(f"{pad}{key_text}:{comment}")
            _emit(value, indent + 1, path, lines, labels)
            continue
        if isinstance(value, list):
            if value and all(not isinstance(item, (dict, list)) for item in value):
                joined = ", ".join(_scalar_yaml(item) for item in value)
                lines.append(f"{pad}{key_text}: [{joined}]{comment}")
            elif not value:
                lines.append(f"{pad}{key_text}: []{comment}")
            else:
                lines.append(f"{pad}{key_text}:{comment}")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{pad}-")
                        _emit(item, indent + 2, path, lines, labels)
                    else:
                        lines.append(f"{pad}  - {_scalar_yaml(item)}")
            continue
        lines.append(f"{pad}{key_text}: {_scalar_yaml(value)}{comment}")


def dump_annotated_yaml(data: dict[str, Any], layout_kind: str | None = None) -> str:
    catalog = load_render_template_schema()
    labels = {
        str(item.get("path")): str(item.get("label") or "").strip()
        for item in catalog["fields"]
        if isinstance(item, dict) and item.get("path")
    }
    kind = str(layout_kind or data.get("layout_kind") or "").strip()
    if kind:
        labels.update(
            {
                str(item.get("path")): str(item.get("label") or "").strip()
                for item in schema_for_layout(kind)["fields"]
                if isinstance(item, dict) and item.get("path")
            }
        )
    lines: list[str] = []
    _emit(data, 0, "", lines, labels)
    return "\n".join(lines) + "\n"
