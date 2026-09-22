"""Field catalog for the render-template editor (TDD)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from services.ingestion.render_templates import list_render_templates

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "config" / "render_template_schema.yaml"

IDENTITY_KEYS = frozenset({"id", "builtin", "layout_kind"})
CONTAINER_PATHS = frozenset({"video.clip_durations_by_count"})


def _leaf_paths(obj, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if path in CONTAINER_PATHS or not isinstance(value, dict):
                paths.add(path)
            else:
                paths |= _leaf_paths(value, path)
    return paths


def test_schema_file_exists_and_loads_groups_and_fields():
    from services.ingestion.render_template_schema import load_render_template_schema

    catalog = load_render_template_schema()
    assert catalog["groups"]
    fields = catalog["fields"]
    assert fields
    by_path = {item["path"]: item for item in fields}
    title = by_path["typography.title_font_size"]
    assert title["label"] == "主标题字号"
    assert title["widget"] == "number"
    assert "help" in title
    assert title["group"] == "typography"


def test_schema_filters_chronicle_only_fields_for_classic_overlay():
    from services.ingestion.render_template_schema import schema_for_layout

    classic = schema_for_layout("classic_overlay")
    paths = {item["path"] for item in classic["fields"]}
    assert "typography.title_font_size" in paths
    assert "canvas.width" in paths
    assert "chrome.brand" not in paths
    assert "palette.accent" not in paths
    assert "layout.card_top_percent" not in paths

    chronicle = schema_for_layout("chronicle_frame")
    chronicle_paths = {item["path"] for item in chronicle["fields"]}
    assert "chrome.brand" in chronicle_paths
    assert "palette.accent" in chronicle_paths
    assert "layout.card_top_percent" in chronicle_paths


def test_schema_covers_builtin_leaf_keys():
    from services.ingestion.render_template_schema import load_render_template_schema

    catalog_paths = {item["path"] for item in load_render_template_schema()["fields"]}
    listed = list_render_templates()["templates"]
    missing: set[str] = set()
    for template in listed:
        for path in _leaf_paths(template):
            if path.split(".", 1)[0] in IDENTITY_KEYS or path in IDENTITY_KEYS:
                continue
            if any(path.startswith(f"{container}.") for container in CONTAINER_PATHS):
                continue
            if path not in catalog_paths:
                missing.add(path)
    assert not missing, f"schema missing paths: {sorted(missing)}"


def test_dump_annotated_yaml_includes_field_labels_as_comments():
    from services.ingestion.render_template_schema import dump_annotated_yaml

    text = dump_annotated_yaml(
        {
            "id": "demo",
            "layout_kind": "classic_overlay",
            "typography": {"title_font_size": 72},
        },
        layout_kind="classic_overlay",
    )
    assert "# 主标题字号" in text
    loaded = yaml.safe_load(text)
    assert loaded["typography"]["title_font_size"] == 72
    assert loaded["id"] == "demo"


def test_dump_annotated_yaml_roundtrips_nested_numbers():
    from services.ingestion.render_template_schema import dump_annotated_yaml

    payload = {
        "id": "demo",
        "layout_kind": "chronicle_frame",
        "canvas": {"width": 1080, "height": 1920, "fps": 24},
        "typography": {"title_font_size": 64, "title_y_percent": 12},
        "palette": {"accent": "#4BE4FF"},
    }
    text = dump_annotated_yaml(payload, layout_kind="chronicle_frame")
    loaded = yaml.safe_load(text)
    assert loaded == payload
    assert "# 强调色" in text or "accent" in text
