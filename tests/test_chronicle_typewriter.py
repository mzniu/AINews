"""TDD tests for chronicle summary typewriter animation."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from services.ingestion.chronicle_render import (
    build_summary_layout,
    chronicle_content_global_t,
    draw_summary_typewriter,
    parse_summary_animation_config,
    render_chronicle_frame,
    summary_visible_chars,
)
from services.ingestion.render_templates import get_render_template


def _template():
    return get_render_template("chronicle_archive_tech_blue")


def _red_image(path: Path) -> Path:
    Image.new("RGB", (800, 600), (220, 30, 30)).save(path)
    return path


def _anim_cfg(**overrides):
    base = parse_summary_animation_config({})
    base.update(overrides)
    return base


def test_parse_summary_animation_defaults_to_static():
    cfg = parse_summary_animation_config({})
    assert cfg["mode"] == "static"
    assert cfg["chars_per_second"] == 14


def test_chronicle_builtin_templates_enable_typewriter():
    for template_id in ("chronicle_archive_tech_blue", "chronicle_evidence_stack"):
        template = get_render_template(template_id)
        cfg = parse_summary_animation_config(template.get("video") or {})
        assert cfg["mode"] == "typewriter"


def test_parse_summary_animation_typewriter_mode():
    cfg = parse_summary_animation_config(
        {"summary_animation": {"mode": "typewriter", "chars_per_second": 10}}
    )
    assert cfg["mode"] == "typewriter"
    assert cfg["chars_per_second"] == 10


def test_summary_visible_chars_zero_before_start_delay():
    anim = _anim_cfg(mode="typewriter", chars_per_second=14, start_delay_sec=0.35)
    assert summary_visible_chars(0.0, total_chars=50, anim_cfg=anim, content_start_t=0.0) == 0
    assert summary_visible_chars(0.34, total_chars=50, anim_cfg=anim, content_start_t=0.0) == 0


def test_summary_visible_chars_linear_typing():
    anim = _anim_cfg(mode="typewriter", chars_per_second=10, start_delay_sec=0.35)
    assert summary_visible_chars(0.35, total_chars=50, anim_cfg=anim, content_start_t=0.0) == 0
    assert summary_visible_chars(1.35, total_chars=50, anim_cfg=anim, content_start_t=0.0) == 10
    assert summary_visible_chars(2.35, total_chars=50, anim_cfg=anim, content_start_t=0.0) == 20


def test_summary_visible_chars_caps_at_total():
    anim = _anim_cfg(mode="typewriter", chars_per_second=14, start_delay_sec=0.35)
    assert summary_visible_chars(100.0, total_chars=30, anim_cfg=anim, content_start_t=0.0) == 30


def test_summary_visible_chars_continues_across_clip_boundary():
    """Second clip must not reset progress (scope: once)."""
    anim = _anim_cfg(mode="typewriter", chars_per_second=14, start_delay_sec=0.35)
    clip1_end = 2.0
    at_clip1_end = summary_visible_chars(clip1_end, total_chars=80, anim_cfg=anim, content_start_t=0.0)
    at_clip2_mid = summary_visible_chars(2.5, total_chars=80, anim_cfg=anim, content_start_t=0.0)
    assert at_clip1_end > 0
    assert at_clip2_mid > at_clip1_end
    assert at_clip2_mid == summary_visible_chars(
        2.5, total_chars=80, anim_cfg=anim, content_start_t=0.0
    )


def test_chronicle_content_global_t_offsets_cover_intro():
    assert chronicle_content_global_t(
        cover_intro_sec=1.0,
        clip_durations=[2.0, 2.0],
        clip_index=1,
        t_within_clip=0.5,
    ) == pytest.approx(3.5)


def test_summary_typewriter_left_align_keeps_x_fixed(monkeypatch):
    positions: list[int] = []
    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        positions.append(int(xy[0]))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    template = _template()
    layout = build_summary_layout(
        draft={"summary": "一二三四五六七八九十", "tags": ""},
        template=template,
        width=1080,
        height=1920,
    )
    base = Image.new("RGB", (1080, 1920), (0, 0, 0))
    anim = _anim_cfg(mode="typewriter")
    draw_summary_typewriter(
        base, layout=layout, visible_char_count=2, global_t=1.0, anim_cfg=anim
    )
    positions.clear()
    draw_summary_typewriter(
        base, layout=layout, visible_char_count=8, global_t=2.0, anim_cfg=anim
    )
    assert positions
    assert positions[0] == layout.summary_x


def test_build_summary_layout_total_chars_matches_flattened_text():
    template = _template()
    layout = build_summary_layout(
        draft={"summary": "小牛说：一二三四五六七八九十", "tags": ""},
        template=template,
        width=1080,
        height=1920,
    )
    assert layout.total_chars == len("一二三四五六七八九十")


def test_draw_summary_typewriter_partial_vs_full_differs(tmp_path):
    template = _template()
    img = _red_image(tmp_path / "shot.jpg")
    base = render_chronicle_frame(
        draft={"main_line1": "标题", "summary": "阿尔法贝塔伽马德尔塔", "tags": ""},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=True,
        include_summary=False,
    )
    layout = build_summary_layout(
        draft={"summary": "阿尔法贝塔伽马德尔塔", "tags": ""},
        template=template,
        width=1080,
        height=1920,
    )
    partial = draw_summary_typewriter(
        base.copy(),
        layout=layout,
        visible_char_count=3,
        global_t=1.0,
        anim_cfg=_anim_cfg(mode="typewriter", show_cursor=True),
    )
    full = draw_summary_typewriter(
        base.copy(),
        layout=layout,
        visible_char_count=layout.total_chars,
        global_t=10.0,
        anim_cfg=_anim_cfg(mode="typewriter", show_cursor=False),
    )
    assert partial.tobytes() != full.tobytes()


def test_build_chronicle_video_clips_typewriter_continues_across_clips(tmp_path):
    from services.ingestion.chronicle_render import build_chronicle_video_clips

    img1 = _red_image(tmp_path / "a.jpg")
    img2 = _red_image(tmp_path / "b.jpg")
    template = _template()
    template = dict(template)
    video = dict(template.get("video") or {})
    video["summary_animation"] = {"mode": "typewriter", "chars_per_second": 14, "start_delay_sec": 0.35}
    template["video"] = video
    clips = build_chronicle_video_clips(
        article_id="tw_test",
        draft={"main_line1": "标题", "summary": "一二三四五六七八九十" * 4, "tags": ""},
        image_paths=[str(img1), str(img2)],
        template=template,
        durations=[2.0, 2.0],
    )
    assert len(clips) == 2
    frame_clip1_end = clips[0].get_frame(1.99)
    frame_clip2_mid = clips[1].get_frame(0.5)
    assert not (frame_clip1_end == frame_clip2_mid).all()


def test_render_chronicle_frame_summary_visible_chars_limits_text():
    template = _template()
    partial = render_chronicle_frame(
        draft={"main_line1": "标题", "summary": "一二三四五六七八九十", "tags": ""},
        image=Image.new("RGB", (800, 600), (200, 0, 0)),
        template=template,
        include_footer=True,
        include_summary=True,
        summary_visible_chars=4,
    )
    full = render_chronicle_frame(
        draft={"main_line1": "标题", "summary": "一二三四五六七八九十", "tags": ""},
        image=Image.new("RGB", (800, 600), (200, 0, 0)),
        template=template,
        include_footer=True,
        include_summary=True,
    )
    assert partial.size == (1080, 1920)
    assert partial.tobytes() != full.tobytes()
