"""Tests for render template load/merge/default (TDD)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from services.ingestion.render_templates import (
    delete_render_template,
    dump_render_template_yaml,
    duplicate_render_template,
    get_default_template_id,
    get_render_template,
    list_render_templates,
    save_render_template,
    save_render_template_from_yaml,
    set_default_template_id,
)


def _write_base(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "version": 1,
                "default_template_id": "flash_news_portrait",
                "templates": [
                    {
                        "id": "flash_news_portrait",
                        "label": "快讯竖屏（默认）",
                        "builtin": True,
                        "layout_kind": "classic_overlay",
                        "canvas": {"width": 1080, "height": 1440, "fps": 24},
                        "background_image": "static/imgs/bg.png",
                        "video": {
                            "clip_durations_by_count": {
                                2: [3.5, 3.5],
                                3: [2.5, 3.0, 3.0],
                            },
                            "clip_sec_when_at_least": {"count": 4, "sec": 2.0},
                            "fallback_clip_sec": 2.5,
                        },
                        "cover": {"enabled": True, "width": 1080, "height": 1440},
                    },
                    {
                        "id": "chronicle_archive_tech_blue",
                        "label": "档案框（科技蓝）",
                        "builtin": True,
                        "layout_kind": "chronicle_frame",
                        "canvas": {"width": 1080, "height": 1920, "fps": 24},
                        "cover": {
                            "enabled": True,
                            "width": 1080,
                            "height": 1440,
                            "crop": "top",
                            "card_images": 1,
                        },
                    },
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _patch_paths(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "render_templates.yaml"
    local_path = tmp_path / "config" / "render_templates.local.yaml"
    _write_base(base_path)
    monkeypatch.setattr(
        "services.ingestion.render_templates.RENDER_TEMPLATES_BASE_PATH", base_path
    )
    monkeypatch.setattr(
        "services.ingestion.render_templates.RENDER_TEMPLATES_LOCAL_PATH", local_path
    )
    return base_path, local_path


def test_default_template_is_flash_news_portrait(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    assert get_default_template_id() == "flash_news_portrait"
    spec = get_render_template(None)
    assert spec["id"] == "flash_news_portrait"
    assert spec["layout_kind"] == "classic_overlay"
    assert spec["canvas"]["width"] == 1080
    assert spec["canvas"]["height"] == 1440


def test_get_render_template_by_id(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    spec = get_render_template("chronicle_archive_tech_blue")
    assert spec["layout_kind"] == "chronicle_frame"
    assert spec["canvas"]["height"] == 1920
    assert spec["cover"]["crop"] == "top"
    assert spec["cover"]["height"] == 1440


def test_unknown_template_id_raises(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unknown_render_template"):
        get_render_template("does_not_exist")


def test_local_overrides_default_template_id(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    set_default_template_id("chronicle_archive_tech_blue")
    assert get_default_template_id() == "chronicle_archive_tech_blue"
    listed = list_render_templates()
    assert listed["default_template_id"] == "chronicle_archive_tech_blue"


def test_cannot_delete_builtin_template(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="builtin"):
        delete_render_template("flash_news_portrait")


def test_unknown_layout_kind_raises_on_resolve(tmp_path, monkeypatch):
    base_path, _local = _patch_paths(tmp_path, monkeypatch)
    data = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    data["templates"][0]["layout_kind"] = "not_a_real_kind"
    base_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown_layout_kind"):
        get_render_template("flash_news_portrait")


def test_repo_builtin_yaml_loads_three_templates():
    listed = list_render_templates()
    ids = {item["id"] for item in listed["templates"]}
    assert "flash_news_portrait" in ids
    assert "chronicle_archive_tech_blue" in ids
    assert "chronicle_evidence_stack" in ids
    base = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config" / "render_templates.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert base["default_template_id"] == "flash_news_portrait"
    flash = get_render_template("flash_news_portrait")
    assert flash["canvas"] == {"width": 1080, "height": 1920, "fps": 24}
    chronicle = get_render_template("chronicle_archive_tech_blue")
    assert chronicle["label"] == "档案框（科技蓝）"
    assert chronicle["cover"]["crop"] == "none"
    assert chronicle["cover"]["height"] == 1920
    assert chronicle["chrome"]["brand"] == "AI 资讯"
    assert chronicle["chrome"]["mark_glyph"] == "牛"
    typo = chronicle["typography"]
    assert typo["subtitle_font_size"] == 52
    assert typo["title_font_size"] == 64
    assert typo["footer_font_size"] >= 40
    layout = chronicle.get("layout") or {}
    assert layout["card_top_percent"] == 33.2
    assert layout["card_bottom_percent"] == 72.8
    assert layout["card_left_percent"] == 3.8
    assert layout["card_right_percent"] == 96.2
    assert layout["card_inset_px"] == 8
    assert layout.get("title_placement") in (None, "above_card")
    assert typo["summary_y_percent"] == 73.2
    motion = (chronicle.get("video") or {}).get("card_motion") or {}
    assert motion["enabled"] is True
    assert motion["random"] is True
    assert float(motion["end_scale"]) >= 1.22
    assert "zoom_in" in motion["effects"]
    assert "pan_left" in motion["effects"]

    evidence = get_render_template("chronicle_evidence_stack")
    assert evidence["label"] == "证据卡"
    assert evidence["builtin"] is True
    assert evidence["layout_kind"] == "chronicle_frame"
    elayout = evidence["layout"]
    assert elayout["title_placement"] == "below_card"
    assert elayout["chrome_placement"] == "footer"
    assert elayout["card_top_percent"] == 5
    assert elayout["card_bottom_percent"] == 52
    assert elayout["card_left_percent"] == 8
    assert elayout["card_right_percent"] == 92
    assert elayout["card_inset_px"] == 16
    assert elayout["title_top_percent"] == 55
    assert elayout["title_rule"] is True
    assert elayout["title_rule_width_px"] == 4
    etypo = evidence["typography"]
    assert etypo["summary_y_percent"] == 75.0
    assert etypo["summary_color"] == "#9EC9D8"
    assert etypo["footer_y_percent"] == 87.0
    emotion = (evidence.get("video") or {}).get("card_motion") or {}
    assert emotion["enabled"] is True
    assert float(emotion["end_scale"]) >= 1.22
    assert evidence["chrome"]["brand"] == "AI 资讯"
    assert evidence["palette"]["accent"] == "#4BE4FF"


def test_repo_builtin_yaml_loads_violet_flash_template():
    listed = list_render_templates()
    ids = {item["id"] for item in listed["templates"]}
    assert "flash_news_violet" in ids
    spec = get_render_template("flash_news_violet")
    assert spec["builtin"] is True
    assert spec["layout_kind"] == "classic_overlay"
    assert spec["label"] == "快讯竖屏（紫夜）"
    assert spec["canvas"] == {"width": 1080, "height": 1920, "fps": 24}
    typo = spec["typography"]
    assert typo["main_line1_color"] == "#FFFFFF"
    assert typo["main_line2_color"] == "#FFFFFF"
    assert typo["subtitle_bar_color"] == "#6B4DFF"
    assert typo["subtitle_text_color"] == "#FFFFFF"
    assert spec["background_image"] == "static/imgs/templates/flash_news_violet/bg.png"
    bg = Path(__file__).resolve().parents[1] / "static" / "imgs" / "templates" / "flash_news_violet" / "bg.png"
    assert bg.is_file()


def test_save_render_template_writes_local_override(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    save_render_template("flash_news_portrait", {"label": "快讯竖屏（改名）"})
    assert get_render_template("flash_news_portrait")["label"] == "快讯竖屏（改名）"
    assert get_render_template("flash_news_portrait")["builtin"] is True


def test_dump_render_template_yaml_roundtrips_id_and_layout(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    text = dump_render_template_yaml("flash_news_portrait")
    loaded = yaml.safe_load(text)
    assert loaded["id"] == "flash_news_portrait"
    assert loaded["layout_kind"] == "classic_overlay"


def test_dump_render_template_yaml_includes_schema_comments(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    text = dump_render_template_yaml("flash_news_portrait")
    assert "width: 1080" in text
    assert "# 画布宽度" in text


def test_save_render_template_from_yaml_replaces_local_entry(tmp_path, monkeypatch):
    _base, local_path = _patch_paths(tmp_path, monkeypatch)
    text = dump_render_template_yaml("flash_news_portrait")
    spec = yaml.safe_load(text)
    spec.setdefault("typography", {})
    spec["typography"]["title_font_size"] = 88
    saved = save_render_template_from_yaml("flash_news_portrait", yaml.dump(spec, allow_unicode=True))
    assert saved["typography"]["title_font_size"] == 88
    local = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    local_row = next(item for item in local["templates"] if item["id"] == "flash_news_portrait")
    assert local_row["typography"]["title_font_size"] == 88


def test_save_render_template_from_yaml_rejects_invalid_yaml(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="invalid_yaml"):
        save_render_template_from_yaml("flash_news_portrait", "id: [\n")


def test_save_render_template_from_yaml_rejects_id_mismatch(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="id"):
        save_render_template_from_yaml(
            "flash_news_portrait",
            "id: other_template\nlayout_kind: classic_overlay\n",
        )


def test_save_render_template_from_yaml_rejects_unknown_layout_kind(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unknown_layout_kind"):
        save_render_template_from_yaml(
            "flash_news_portrait",
            "id: flash_news_portrait\nlayout_kind: not_a_real_kind\n",
        )


def test_duplicate_render_template_is_not_builtin(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    copied = duplicate_render_template("flash_news_portrait", new_id="flash_copy", label="副本")
    assert copied["id"] == "flash_copy"
    assert copied["builtin"] is False
    delete_render_template("flash_copy")
    with pytest.raises(ValueError, match="unknown_render_template"):
        get_render_template("flash_copy")
