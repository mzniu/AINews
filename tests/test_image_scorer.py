"""Tests for image relevance rule scoring (prefilter, grades, ranking, auto-select)."""
from __future__ import annotations

from pathlib import Path

import pytest

from services.ingestion.image_scorer import (
    ImageScoreResult,
    ScorableImage,
    compute_final_score,
    compute_media_bonuses,
    compute_orientation_adjustments,
    grade_from_total,
    is_animation_raster,
    load_image_scoring_config,
    pick_auto_selected,
    prefilter_image,
    rank_evaluations,
)


@pytest.fixture
def cfg():
    return load_image_scoring_config()


def _scorable(
    *,
    source_id: str = "img1",
    url: str = "https://cdn.example.com/photo.jpg",
    local_path: str | None = "/data/ingested/test/img_001.jpg",
    sort_order: int = 0,
    origin: str = "article_body",
    download_status: str = "ok",
    source_type: str = "article_image",
) -> ScorableImage:
    return ScorableImage(
        source_type=source_type,
        source_id=source_id,
        original_url=url,
        local_path=local_path,
        sort_order=sort_order,
        origin=origin,
        download_status=download_status,
    )


def test_load_image_scoring_config_has_weights(cfg):
    assert cfg["weights"]["flash_fit"] >= 0.15
    assert cfg["weights"]["figure_prominence"] >= 0.08
    assert abs(sum(cfg["weights"].values()) - 1.0) < 0.01
    assert cfg["grades"]["A"] == 80
    assert cfg["auto_select"]["max_count"] == 4
    assert cfg["scorer_version"] == "1.2"


def test_prefilter_skips_failed_download(cfg):
    result = prefilter_image(
        _scorable(download_status="failed"),
        local_file=None,
        config=cfg,
    )
    assert result.skip is True


def test_prefilter_forces_d_grade_for_logo_url(cfg, tmp_path):
    img_path = tmp_path / "logo_test.jpg"
    from PIL import Image

    Image.new("RGB", (800, 600), color="gray").save(img_path)
    result = prefilter_image(
        _scorable(
            url="https://cdn.example.com/site-logo-v2.png",
            local_path=str(img_path),
        ),
        local_file=img_path,
        config=cfg,
    )
    assert result.skip_vl is True
    assert result.forced_grade == "D"


def test_prefilter_forces_d_for_tiny_dimensions(cfg, tmp_path):
    # 100x80 image — below min 220x140
    img_path = tmp_path / "small.jpg"
    try:
        from PIL import Image

        Image.new("RGB", (100, 80), color="red").save(img_path)
    except ImportError:
        pytest.skip("Pillow not installed")

    result = prefilter_image(
        _scorable(local_path=str(img_path)),
        local_file=img_path,
        config=cfg,
    )
    assert result.skip_vl is True
    assert result.forced_grade == "D"


def test_compute_final_score_from_vl_dimensions(cfg):
    vl_payload = {
        "dimensions": {
            "topic_relevance": {"score": 9, "signals": ["DeepSeek"]},
            "info_value": {"score": 8, "signals": ["产品截图"]},
            "visual_quality": {"score": 9, "signals": ["清晰"]},
            "flash_fit": {"score": 8, "signals": ["主体突出"]},
            "cover_fit": {"score": 9, "signals": ["适合封面"]},
            "figure_prominence": {"score": 8, "signals": ["黄仁勋"]},
            "compliance": {"score": 9, "signals": ["无水印"]},
        },
        "penalties": [],
        "caption": "DeepSeek 界面截图",
        "verdict": "首选配图",
        "reject": False,
    }
    result = compute_final_score(
        vl_payload,
        extra_penalties=[],
        width=1920,
        height=1080,
        config=cfg,
    )
    assert result.total >= 80
    assert result.grade == "A"
    assert result.caption == "DeepSeek 界面截图"
    assert "cover_fit" in (result.breakdown or {}).get("dimensions", {})


def test_compute_final_score_applies_penalties(cfg):
    vl_payload = {
        "dimensions": {
            "topic_relevance": {"score": 7, "signals": []},
            "info_value": {"score": 7, "signals": []},
            "visual_quality": {"score": 7, "signals": []},
            "flash_fit": {"score": 7, "signals": []},
            "compliance": {"score": 5, "signals": ["水印"]},
        },
        "penalties": [{"reason": "watermark", "points": 15}],
        "caption": "带水印图",
        "verdict": "可用",
        "reject": False,
    }
    base = compute_final_score(vl_payload, extra_penalties=[], config=cfg)
    with_extra = compute_final_score(
        vl_payload,
        extra_penalties=[{"reason": "duplicate", "points": 15}],
        config=cfg,
    )
    assert with_extra.total < base.total


def test_prefilter_adds_watermark_penalty_when_detected(cfg, tmp_path, monkeypatch):
    img_path = tmp_path / "wm.jpg"
    from PIL import Image

    Image.new("RGB", (800, 600), color="gray").save(img_path)
    monkeypatch.setattr(
        "services.image_watermark_detect.has_likely_watermark",
        lambda _path, **_kwargs: True,
    )
    cfg_wm = dict(cfg)
    cfg_wm["prefilter"] = {**(cfg.get("prefilter") or {}), "watermark_detect": True}
    result = prefilter_image(
        _scorable(local_path=str(img_path)),
        local_file=img_path,
        config=cfg_wm,
    )
    assert result.skip_vl is False
    assert any(p.get("reason") == "watermark" for p in result.base_penalties)


def test_grade_from_total_boundaries(cfg):
    assert grade_from_total(85, cfg) == "A"
    assert grade_from_total(80, cfg) == "A"
    assert grade_from_total(79, cfg) == "B"
    assert grade_from_total(39, cfg) == "D"


def test_pick_auto_selected_prefers_a_grade(cfg):
    evaluations = [
        ImageScoreResult(
            source_type="article_image",
            source_id="a1",
            original_url="u1",
            total=85,
            grade="A",
            rank=1,
            sort_order=0,
            origin="cover",
        ),
        ImageScoreResult(
            source_type="article_image",
            source_id="b1",
            original_url="u2",
            total=70,
            grade="B",
            rank=2,
            sort_order=1,
            origin="article_body",
        ),
    ]
    picked = pick_auto_selected(evaluations, config=cfg)
    assert len(picked) == 1
    assert picked[0].source_id == "a1"


def test_pick_auto_selected_falls_back_to_b_when_no_a(cfg):
    evaluations = [
        ImageScoreResult(
            source_type="article_image",
            source_id="b1",
            original_url="u1",
            total=70,
            grade="B",
            rank=1,
            sort_order=0,
            origin="cover",
        ),
        ImageScoreResult(
            source_type="article_image",
            source_id="b2",
            original_url="u2",
            total=65,
            grade="B",
            rank=2,
            sort_order=1,
            origin="article_body",
        ),
    ]
    picked = pick_auto_selected(evaluations, config=cfg)
    assert len(picked) == 2
    assert all(e.grade == "B" for e in picked)


def test_pick_auto_selected_supplements_with_c_when_below_min(cfg):
    cfg = dict(cfg)
    cfg["auto_select"] = {
        **(cfg.get("auto_select") or {}),
        "min_count": 2,
        "supplement_grade": "C",
        "max_count": 4,
    }
    evaluations = [
        ImageScoreResult(
            source_type="article_image",
            source_id="b1",
            original_url="u1",
            total=72.6,
            grade="B",
            rank=1,
            sort_order=0,
            origin="cover",
        ),
        ImageScoreResult(
            source_type="article_image",
            source_id="c1",
            original_url="u2",
            total=54.6,
            grade="C",
            rank=2,
            sort_order=1,
            origin="article_body",
        ),
        ImageScoreResult(
            source_type="article_image",
            source_id="c2",
            original_url="u3",
            total=52.0,
            grade="C",
            rank=3,
            sort_order=2,
            origin="article_body",
        ),
    ]
    picked = pick_auto_selected(evaluations, config=cfg)
    assert len(picked) == 2
    assert picked[0].source_id == "b1"
    assert picked[1].source_id == "c1"


def test_rank_evaluations_orders_by_score_then_source(cfg):
    items = [
        ImageScoreResult(
            source_type="story_asset",
            source_id="s1",
            original_url="u1",
            total=90,
            grade="A",
            rank=0,
            sort_order=0,
            origin="story_related",
        ),
        ImageScoreResult(
            source_type="article_image",
            source_id="a1",
            original_url="u2",
            total=90,
            grade="A",
            rank=0,
            sort_order=0,
            origin="cover",
        ),
    ]
    ranked = rank_evaluations(items)
    assert ranked[0].source_type == "article_image"
    assert ranked[0].relevance_rank == 1
    assert ranked[1].relevance_rank == 2


def test_orientation_bonus_for_landscape(cfg):
    bonuses, penalties = compute_orientation_adjustments(1600, 900, config=cfg)
    assert any(b["reason"] == "landscape" for b in bonuses)
    assert not any(p["reason"] == "portrait" for p in penalties)


def test_orientation_penalty_for_portrait(cfg):
    bonuses, penalties = compute_orientation_adjustments(600, 1200, config=cfg)
    assert any(p["reason"] == "portrait" for p in penalties)
    assert not any(b["reason"] == "landscape" for b in bonuses)


def test_prefilter_forces_d_grade_for_chapter_title_url(cfg, tmp_path):
    img_path = tmp_path / "chapter_header.jpg"
    from PIL import Image

    Image.new("RGB", (800, 600), color="gray").save(img_path)
    result = prefilter_image(
        _scorable(
            url="https://cdn.example.com/article/chapter-01-heading.png",
            local_path=str(img_path),
        ),
        local_file=img_path,
        config=cfg,
    )
    assert result.skip_vl is True
    assert result.forced_grade == "D"


def test_is_animation_raster_detects_gif(tmp_path):
    gif_path = tmp_path / "demo.gif"
    from PIL import Image

    Image.new("RGB", (100, 100), color="red").save(gif_path, save_all=True, append_images=[], duration=100, loop=0)
    assert is_animation_raster(gif_path) is True


def test_compute_media_bonuses_for_gif(cfg, tmp_path):
    gif_path = tmp_path / "clip.gif"
    from PIL import Image

    Image.new("RGB", (200, 200), color="blue").save(gif_path)
    bonuses = compute_media_bonuses(gif_path, config=cfg)
    assert any(b.get("reason") == "animated" for b in bonuses)
    assert bonuses[0]["points"] == cfg["bonuses"]["animated"]


def test_compute_final_score_applies_animated_bonus(cfg):
    vl_payload = {
        "dimensions": {
            "topic_relevance": {"score": 8, "signals": []},
            "info_value": {"score": 8, "signals": []},
            "visual_quality": {"score": 8, "signals": []},
            "flash_fit": {"score": 8, "signals": []},
            "cover_fit": {"score": 7, "signals": []},
            "figure_prominence": {"score": 7, "signals": []},
            "compliance": {"score": 9, "signals": []},
        },
        "penalties": [],
        "reject": False,
    }
    base = compute_final_score(vl_payload, config=cfg, width=1280, height=720)
    with_anim = compute_final_score(
        vl_payload,
        extra_bonuses=[{"reason": "animated", "points": cfg["bonuses"]["animated"]}],
        config=cfg,
        width=1280,
        height=720,
    )
    assert with_anim.total > base.total
    assert with_anim.breakdown.get("is_animated") is True


def test_rank_prefers_landscape_when_scores_equal(cfg):
    high_cover = {
        "topic_relevance": {"score": 8},
        "info_value": {"score": 8},
        "visual_quality": {"score": 8},
        "flash_fit": {"score": 8},
        "cover_fit": {"score": 9},
        "figure_prominence": {"score": 5},
        "compliance": {"score": 8},
    }
    portrait = ImageScoreResult(
        source_type="article_image",
        source_id="p1",
        original_url="u1",
        total=75,
        grade="B",
        width=600,
        height=1200,
        breakdown={"dimensions": high_cover},
    )
    landscape = ImageScoreResult(
        source_type="article_image",
        source_id="l1",
        original_url="u2",
        total=75,
        grade="B",
        width=1600,
        height=900,
        breakdown={"dimensions": high_cover},
    )
    ranked = rank_evaluations([portrait, landscape])
    assert ranked[0].source_id == "l1"


def test_rank_prefers_animated_when_scores_equal(cfg):
    dims = {
        "topic_relevance": {"score": 8},
        "info_value": {"score": 8},
        "visual_quality": {"score": 8},
        "flash_fit": {"score": 8},
        "cover_fit": {"score": 8},
        "figure_prominence": {"score": 5},
        "compliance": {"score": 8},
    }
    static_img = ImageScoreResult(
        source_type="article_image",
        source_id="static",
        original_url="u1",
        total=75,
        grade="B",
        width=1280,
        height=720,
        breakdown={"dimensions": dims},
    )
    animated = ImageScoreResult(
        source_type="article_image",
        source_id="gif1",
        original_url="u2",
        total=75,
        grade="B",
        width=1280,
        height=720,
        is_animated=True,
        breakdown={"dimensions": dims, "is_animated": True, "bonuses": [{"reason": "animated", "points": 8}]},
    )
    ranked = rank_evaluations([static_img, animated])
    assert ranked[0].source_id == "gif1"


def test_rank_prefers_figure_prominence_when_scores_equal(cfg):
    dims_low_figure = {
        "topic_relevance": {"score": 8},
        "info_value": {"score": 8},
        "visual_quality": {"score": 8},
        "flash_fit": {"score": 8},
        "cover_fit": {"score": 8},
        "figure_prominence": {"score": 4},
        "compliance": {"score": 8},
    }
    dims_high_figure = {**dims_low_figure, "figure_prominence": {"score": 9, "signals": ["马斯克"]}}
    a = ImageScoreResult(
        source_type="article_image",
        source_id="low",
        original_url="u1",
        total=75,
        grade="B",
        width=1200,
        height=800,
        breakdown={"dimensions": dims_low_figure},
    )
    b = ImageScoreResult(
        source_type="article_image",
        source_id="high",
        original_url="u2",
        total=75,
        grade="B",
        width=1200,
        height=800,
        breakdown={"dimensions": dims_high_figure},
    )
    ranked = rank_evaluations([a, b])
    assert ranked[0].source_id == "high"
