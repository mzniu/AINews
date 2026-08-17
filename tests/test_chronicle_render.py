"""Tests for chronicle-frame still compositor and cover-safe crop."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from services.ingestion.chronicle_render import (
    crop_top_cover,
    hero_inner_box,
    hero_motion_at,
    ken_burns_scale_at,
    pick_card_motion_effect,
    render_chronicle_cover,
    render_chronicle_frame,
    scaled_hero,
)
from services.ingestion.render_templates import get_render_template


GOLD = (232, 197, 71)


def _template():
    return get_render_template("chronicle_archive_tech_blue")


def _evidence_template():
    return get_render_template("chronicle_evidence_stack")


def _red_image(path: Path) -> Path:
    Image.new("RGB", (800, 600), (220, 30, 30)).save(path)
    return path


def test_crop_top_cover_keeps_top_pixels():
    frame = Image.new("RGB", (1080, 1920), (0, 0, 0))
    frame.putpixel((10, 10), (255, 0, 0))
    frame.putpixel((10, 1500), (0, 255, 0))
    cover = crop_top_cover(frame, 1080, 1440)
    assert cover.size == (1080, 1440)
    assert cover.getpixel((10, 10)) == (255, 0, 0)
    with pytest.raises(IndexError):
        cover.getpixel((10, 1500))


def test_chronicle_cover_matches_video_canvas(tmp_path):
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas = template.get("canvas") or {}
    result = render_chronicle_cover(
        article_id="art_c",
        draft={
            "main_line1": "突发！测试标题",
            "sub_title": "副标题一行",
            "sub_title2": "钩子第二行",
            "summary": "小牛说：这是摘要",
            "tags": "#人工智能 #大模型",
        },
        image_path=str(img),
        template=template,
        output_dir=tmp_path,
    )
    assert result["success"] is True
    saved = Image.open(tmp_path / Path(result["cover_path"]).name)
    assert saved.size == (int(canvas.get("width") or 1080), int(canvas.get("height") or 1920))
    assert saved.size == (1080, 1920)


def test_chronicle_cover_skips_summary_keeps_chrome(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    result = render_chronicle_cover(
        article_id="art_footer",
        draft={
            "main_line1": "突发！测试标题",
            "sub_title": "副标题一行",
            "sub_title2": "钩子第二行",
            "summary": "小牛说：这是摘要正文",
            "tags": "#大模型",
        },
        image_path=str(img),
        template=_template(),
        output_dir=tmp_path,
    )
    assert result["success"] is True
    saved = Image.open(tmp_path / Path(result["cover_path"]).name)
    assert saved.size == (1080, 1920)
    labels = [text for _, text in drawn]
    footer_left = str((_template().get("chrome") or {}).get("footer_left") or "快讯档案")
    assert footer_left in labels
    assert any("测试标题" in text for text in labels)
    assert not any("这是摘要正文" in text for text in labels)
    footer_y = next(xy[1] for xy, text in drawn if text == footer_left)
    assert footer_y > 1440


def test_chronicle_card_contains_hero_image_not_gold(tmp_path):
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    frame = render_chronicle_frame(
        draft={"main_line1": "突发！标题", "tags": "#大模型"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    # Card interior should pick up the red hero crop.
    sample = frame.getpixel((540, 980))
    assert sample[0] > 150
    assert sample[1] < 80
    # No gold accent leftover from the reference poster.
    pixels = list(frame.get_flattened_data()) if hasattr(frame, "get_flattened_data") else list(frame.getdata())
    goldish = sum(1 for r, g, b in pixels if abs(r - GOLD[0]) < 20 and abs(g - GOLD[1]) < 20 and abs(b - GOLD[2]) < 25)
    assert goldish < 50


def test_chronicle_does_not_draw_follow_or_source(tmp_path, monkeypatch):
    drawn: list[str] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append(str(text))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    render_chronicle_frame(
        draft={"main_line1": "突发！标题", "tags": "#人工智能 #Agent"},
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_footer=True,
        source_name="量子位",
    )
    blob = " ".join(drawn)
    assert "Follow" not in blob
    assert "量子位" not in blob
    assert "Agent" not in blob
    assert "小牛聊AI" in blob
    assert "EVIDENCE" not in blob


def test_chronicle_omits_card_keyword(tmp_path, monkeypatch):
    drawn: list[str] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append(str(text))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    render_chronicle_frame(
        draft={
            "main_line1": "突发！标题",
            "tags": "#大模型 #Agent",
            "highlight_keywords": ["点火"],
        },
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_footer=False,
    )
    blob = " ".join(drawn)
    assert "大模型" not in blob
    assert "Agent" not in blob
    assert "点火" not in blob
    assert "快讯" not in blob


def test_chronicle_hero_fills_card_without_keyword_gutter(tmp_path):
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_top = int(canvas_h * float((template.get("layout") or {}).get("card_top_percent", 32)) / 100.0)
    frame = render_chronicle_frame(
        draft={"main_line1": "突发！标题", "tags": "#大模型"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    sample = frame.getpixel((540, card_top + 24))
    assert sample[0] > 150
    assert sample[1] < 80


def test_chronicle_title_highlights_keyword(tmp_path, monkeypatch):
    painted: list[tuple[str, object]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        painted.append((str(text), kwargs.get("fill")))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    render_chronicle_frame(
        draft={
            "main_line1": "突发！DeepSeek发布",
            "highlight_keywords": ["DeepSeek"],
        },
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_footer=False,
    )
    hi = [(text, fill) for text, fill in painted if text == "DeepSeek"]
    assert hi
    assert hi[0][1] != (244, 247, 250)


def test_chronicle_summary_highlights_keyword(tmp_path, monkeypatch):
    painted: list[tuple[object, str, object]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        painted.append((xy, str(text), kwargs.get("fill")))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    render_chronicle_frame(
        draft={
            "main_line1": "突发！标题",
            "summary": "小牛说：DeepSeek发布了新模型",
            "highlight_keywords": ["DeepSeek"],
        },
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=True,
    )
    footer_hits = [
        (xy, text, fill)
        for xy, text, fill in painted
        if text == "DeepSeek" and xy[1] >= int(canvas_h * 0.70)
    ]
    assert footer_hits
    assert footer_hits[0][2] != (244, 247, 250)


def test_chronicle_header_has_extra_top_space(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    render_chronicle_frame(
        draft={"main_line1": "突发！标题"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    brand_y = next(xy[1] for xy, text in drawn if text == "小牛聊AI")
    assert brand_y >= int(canvas_h * 0.08)


def test_chronicle_summary_moved_up_10_percent(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    render_chronicle_frame(
        draft={"main_line1": "突发！标题", "summary": "小牛说：这是摘要正文"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=True,
    )
    summary_y = next(xy[1] for xy, text in drawn if "这是摘要正文" in text)
    summary_pct = float((template.get("typography") or {}).get("summary_y_percent", 75.2)) / 100.0
    assert summary_y == int(canvas_h * summary_pct)
    assert abs(summary_pct - 0.702) < 0.001
    assert int(canvas_h * 0.68) < summary_y < int(canvas_h * 0.73)


def test_chronicle_card_and_summary_shifted_up_from_header_pad(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_top_pct = float((template.get("layout") or {}).get("card_top_percent", 32)) / 100.0
    frame = render_chronicle_frame(
        draft={"main_line1": "突发！标题", "summary": "小牛说：这是摘要正文"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=True,
    )
    card_top = int(canvas_h * card_top_pct)
    sample = frame.getpixel((540, card_top + 24))
    assert sample[0] > 150
    assert sample[1] < 80
    summary_y = next(xy[1] for xy, text in drawn if "这是摘要正文" in text)
    assert summary_y < int(canvas_h * 0.78)


def test_chronicle_footer_chrome_sits_below_summary(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    render_chronicle_frame(
        draft={"main_line1": "突发！标题", "summary": "小牛说：这是摘要正文"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=True,
    )
    summary_y = next(xy[1] for xy, text in drawn if "这是摘要正文" in text)
    footer_left = str((template.get("chrome") or {}).get("footer_left") or "快讯档案")
    footer_y = next(xy[1] for xy, text in drawn if text == footer_left)
    footer_pct = float((template.get("typography") or {}).get("footer_y_percent", 85.2)) / 100.0
    assert footer_y == int(canvas_h * (footer_pct + 0.02))
    assert footer_y > summary_y
    assert footer_y > int(canvas_h * 0.84)


def test_chronicle_brand_sub_sits_below_brand(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    render_chronicle_frame(
        draft={"main_line1": "突发！标题"},
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_footer=False,
    )
    brand_y = next(xy[1] for xy, text in drawn if text == "小牛聊AI")
    sub_y = next(xy[1] for xy, text in drawn if "粉碎AI信息差" in text)
    assert sub_y >= brand_y + 48


def test_chronicle_footer_omits_year(tmp_path, monkeypatch):
    from datetime import datetime

    drawn: list[str] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append(str(text))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    render_chronicle_frame(
        draft={"main_line1": "突发！标题", "summary": "小牛说：摘要"},
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_footer=True,
    )
    year = str(datetime.now().year)
    assert year not in drawn
    assert any(text.startswith("RECORD") for text in drawn)


def test_chronicle_backdrop_has_tech_depth(tmp_path):
    img = _red_image(tmp_path / "shot.jpg")
    frame = render_chronicle_frame(
        draft={"main_line1": "突发！标题"},
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_hero=False,
        include_footer=False,
    )
    crop = frame.crop((720, 220, 960, 400))
    arr = np.array(crop, dtype=np.float32)
    assert float(arr.std()) > 6.0
    cyanish = int(np.sum((arr[:, :, 2] > arr[:, :, 0] + 8) & (arr[:, :, 2] > 28)))
    assert cyanish > 200


def test_ken_burns_scale_eases_from_start_to_end():
    assert ken_burns_scale_at(0, 4, 1.0, 1.15) == 1.0
    assert ken_burns_scale_at(4, 4, 1.0, 1.15) == 1.15
    mid = ken_burns_scale_at(2, 4, 1.0, 1.15)
    assert 1.0 < mid < 1.15


def test_scaled_hero_zoom_changes_pixels(tmp_path):
    img = Image.new("RGB", (200, 200), (0, 0, 180))
    img.putpixel((100, 100), (255, 0, 0))
    a = scaled_hero(img, 80, 80, 1.0)
    b = scaled_hero(img, 80, 80, 1.5)
    assert a.size == b.size == (80, 80)
    assert list(a.getdata()) != list(b.getdata())


def test_chronicle_layout_reads_card_and_summary_percents():
    template = _template()
    layout = template.get("layout") or {}
    typo = template.get("typography") or {}
    assert float(layout["card_top_percent"]) == 35
    assert float(layout["card_bottom_percent"]) == 71
    assert float(typo["summary_y_percent"]) == 70.2
    left, top, right, bottom = hero_inner_box(1080, 1920, template)
    assert top == int(1920 * 0.35) + 16
    assert bottom == int(1920 * 0.71) - 16


def test_hero_motion_zoom_in_is_stronger_than_old_ken_burns():
    start = hero_motion_at(0, 4, "zoom_in", end_scale=1.22, pan=0.7)
    end = hero_motion_at(4, 4, "zoom_in", end_scale=1.22, pan=0.7)
    assert start == (1.0, 0.0, 0.0)
    assert end[0] == 1.22
    assert end[0] > 1.15


def test_hero_motion_pan_left_travels_across_x():
    start = hero_motion_at(0, 2, "pan_left", end_scale=1.22, pan=0.7)
    end = hero_motion_at(2, 2, "pan_left", end_scale=1.22, pan=0.7)
    assert start[0] == end[0] == 1.22
    assert start[1] > 0
    assert end[1] < 0


def test_pick_card_motion_effect_is_stable_and_varies_by_index():
    effects = ["zoom_in", "pan_left", "zoom_out", "pan_up"]
    a = pick_card_motion_effect(effects, seed="art1", index=0)
    b = pick_card_motion_effect(effects, seed="art1", index=0)
    c = pick_card_motion_effect(effects, seed="art1", index=1)
    assert a == b
    assert a in effects
    assert c in effects


def test_scaled_hero_pan_offset_changes_crop():
    img = Image.new("RGB", (200, 200), (0, 0, 180))
    img.putpixel((40, 100), (255, 0, 0))
    img.putpixel((160, 100), (0, 255, 0))
    left = scaled_hero(img, 80, 80, 1.5, offset_x=-1.0)
    right = scaled_hero(img, 80, 80, 1.5, offset_x=1.0)
    assert list(left.getdata()) != list(right.getdata())


def test_archive_title_stays_above_card(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_top = int(canvas_h * float((template.get("layout") or {}).get("card_top_percent", 35)) / 100.0)
    render_chronicle_frame(
        draft={"main_line1": "突发！档案标题"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    title_y = next(xy[1] for xy, text in drawn if "档案标题" in text)
    assert title_y < card_top


def test_evidence_title_sits_below_card(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_bottom = int(
        canvas_h * float((template.get("layout") or {}).get("card_bottom_percent", 52)) / 100.0
    )
    title_top = int(
        canvas_h * float((template.get("layout") or {}).get("title_top_percent", 55)) / 100.0
    )
    render_chronicle_frame(
        draft={"main_line1": "突发！证据标题"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    title_y = next(xy[1] for xy, text in drawn if "证据标题" in text)
    assert title_y >= card_bottom
    assert title_y == title_top


def test_unknown_title_placement_keeps_archive_order(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    template.setdefault("layout", {})["title_placement"] = "sideways"
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_top = int(canvas_h * float(template["layout"].get("card_top_percent", 35)) / 100.0)
    render_chronicle_frame(
        draft={"main_line1": "突发！未知排版"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    title_y = next(xy[1] for xy, text in drawn if "未知排版" in text)
    assert title_y < card_top


def test_evidence_title_rule_uses_accent(tmp_path):
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    canvas_w = int((template.get("canvas") or {}).get("width") or 1080)
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    title_top = int(canvas_h * float(template["layout"]["title_top_percent"]) / 100.0)
    rule_x = int(canvas_w * 0.045)
    frame = render_chronicle_frame(
        draft={"main_line1": "突发！证据标题"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    sample = frame.getpixel((rule_x + 1, title_top + 20))
    assert sample[2] > sample[0] + 40
    assert sample[1] > 150


def test_evidence_summary_uses_summary_color(tmp_path, monkeypatch):
    painted: list[tuple[object, str, object]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        painted.append((xy, str(text), kwargs.get("fill")))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    render_chronicle_frame(
        draft={
            "main_line1": "突发！证据标题",
            "summary": "小牛说：这是评论腔摘要",
        },
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=True,
    )
    hits = [(text, fill) for _xy, text, fill in painted if "这是评论腔摘要" in text]
    assert hits
    assert hits[0][1] == (158, 201, 216)


def test_archive_summary_stays_white_without_summary_color(tmp_path, monkeypatch):
    painted: list[tuple[str, object]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        painted.append((str(text), kwargs.get("fill")))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    render_chronicle_frame(
        draft={"main_line1": "突发！档案标题", "summary": "小牛说：这是摘要正文"},
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_footer=True,
    )
    hits = [(text, fill) for text, fill in painted if "这是摘要正文" in text]
    assert hits
    assert hits[0][1] == (244, 247, 250)


def test_evidence_cover_skips_summary_keeps_title(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    result = render_chronicle_cover(
        article_id="art_evidence_cover",
        draft={
            "main_line1": "突发！证据封面标题",
            "summary": "小牛说：这是不应出现的摘要",
        },
        image_path=str(img),
        template=template,
        output_dir=tmp_path,
    )
    assert result["success"] is True
    labels = [text for _, text in drawn]
    assert any("证据封面标题" in text for text in labels)
    assert not any("这是不应出现的摘要" in text for text in labels)
    footer_left = str((template.get("chrome") or {}).get("footer_left") or "AI 快讯")
    assert footer_left in labels
