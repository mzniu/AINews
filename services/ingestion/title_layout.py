"""Title block left/width from render-template YAML."""
from __future__ import annotations

from typing import Any

DEFAULT_CLASSIC_TITLE_X_PERCENT = 8.0
DEFAULT_CHRONICLE_TITLE_RULE_X_PERCENT = 4.5
DEFAULT_CHRONICLE_TITLE_X_PAD_PX = 18
DEFAULT_CHRONICLE_TITLE_RIGHT_PAD_PX = 20
DEFAULT_CHRONICLE_FRAME_INSET_PERCENT = 2.4


def _pct(percent: float, total: int) -> int:
    return int(total * (float(percent) / 100.0))


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def resolve_title_box(width: int, template: dict[str, Any] | None = None) -> tuple[int, int, int]:
    """Return (title_x, title_max_w, rule_x) in pixels."""
    spec = template or {}
    typo = spec.get("typography") or {}
    layout = spec.get("layout") or {}
    kind = str(spec.get("layout_kind") or "classic_overlay").strip()
    x_percent = _optional_float(typo.get("title_x_percent"))
    width_percent = _optional_float(typo.get("title_width_percent"))

    if kind == "chronicle_frame":
        inset = _pct(DEFAULT_CHRONICLE_FRAME_INSET_PERCENT, width)
        rule_percent = _optional_float(layout.get("title_rule_x_percent"))
        if rule_percent is None:
            rule_percent = DEFAULT_CHRONICLE_TITLE_RULE_X_PERCENT
        rule_x = _pct(rule_percent, width)
        pad = _optional_int(layout.get("title_x_pad_px"), DEFAULT_CHRONICLE_TITLE_X_PAD_PX)
        right_pad = _optional_int(
            layout.get("title_right_pad_px"), DEFAULT_CHRONICLE_TITLE_RIGHT_PAD_PX
        )
        title_x = _pct(x_percent, width) if x_percent is not None else rule_x + pad
        if width_percent is not None:
            title_max_w = _pct(width_percent, width)
        else:
            title_max_w = width - title_x - inset - right_pad
        return title_x, max(1, title_max_w), rule_x

    title_x = _pct(x_percent if x_percent is not None else DEFAULT_CLASSIC_TITLE_X_PERCENT, width)
    if width_percent is not None:
        title_max_w = _pct(width_percent, width)
    else:
        title_max_w = width - 2 * title_x
    return title_x, max(1, title_max_w), title_x
