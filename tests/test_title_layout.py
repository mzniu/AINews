"""Title block geometry from render-template YAML (TDD)."""
from __future__ import annotations

from services.ingestion.title_layout import resolve_title_box


def test_classic_defaults_match_eight_percent_side_margins():
    title_x, title_max_w, _rule_x = resolve_title_box(
        1080, {"layout_kind": "classic_overlay"}
    )
    margin = int(1080 * 0.08)
    assert title_x == margin
    assert title_max_w == 1080 - 2 * margin


def test_classic_uses_title_x_and_width_percent():
    title_x, title_max_w, _rule_x = resolve_title_box(
        1080,
        {
            "layout_kind": "classic_overlay",
            "typography": {"title_x_percent": 5, "title_width_percent": 70},
        },
    )
    assert title_x == int(1080 * 0.05)
    assert title_max_w == int(1080 * 0.70)


def test_chronicle_defaults_match_hardcoded_geometry():
    width = 1080
    title_x, title_max_w, rule_x = resolve_title_box(
        width, {"layout_kind": "chronicle_frame"}
    )
    inset = int(width * 0.024)
    assert rule_x == int(width * 0.045)
    assert title_x == rule_x + 18
    assert title_max_w == width - title_x - inset - 20


def test_chronicle_uses_title_width_and_x_percent():
    width = 1080
    title_x, title_max_w, rule_x = resolve_title_box(
        width,
        {
            "layout_kind": "chronicle_frame",
            "typography": {"title_x_percent": 10, "title_width_percent": 60},
            "layout": {"title_rule_x_percent": 8, "title_x_pad_px": 12, "title_right_pad_px": 30},
        },
    )
    assert title_x == int(width * 0.10)
    assert title_max_w == int(width * 0.60)
    assert rule_x == int(width * 0.08)


def test_chronicle_width_percent_keeps_default_left_when_x_omitted():
    width = 1080
    default_x, _default_w, default_rule = resolve_title_box(
        width, {"layout_kind": "chronicle_frame"}
    )
    title_x, title_max_w, rule_x = resolve_title_box(
        width,
        {
            "layout_kind": "chronicle_frame",
            "typography": {"title_width_percent": 50},
        },
    )
    assert title_x == default_x
    assert rule_x == default_rule
    assert title_max_w == int(width * 0.50)


def test_chronicle_zero_pad_is_not_treated_as_missing():
    width = 1080
    title_x, title_max_w, rule_x = resolve_title_box(
        width,
        {
            "layout_kind": "chronicle_frame",
            "layout": {
                "title_rule_x_percent": 4.5,
                "title_x_pad_px": 0,
                "title_right_pad_px": 0,
            },
        },
    )
    inset = int(width * 0.024)
    assert rule_x == int(width * 0.045)
    assert title_x == rule_x
    assert title_max_w == width - title_x - inset
