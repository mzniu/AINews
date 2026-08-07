"""Rule-based image relevance scoring for flash-news配图筛选."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from src.utils.config import Config

_CONFIG_PATH = Config.ROOT_DIR / "config" / "image_scoring.yaml"

VALID_GRADES = frozenset({"A", "B", "C", "D"})

_DIMENSION_KEYS = (
    "topic_relevance",
    "info_value",
    "visual_quality",
    "flash_fit",
    "cover_fit",
    "figure_prominence",
    "compliance",
)


@dataclass
class ScorableImage:
    source_type: Literal["article_image", "story_asset"]
    source_id: str
    original_url: str
    local_path: str | None
    sort_order: int
    origin: str
    download_status: str


@dataclass
class PreFilterResult:
    skip: bool = False
    skip_vl: bool = False
    forced_grade: str | None = None
    forced_score: float | None = None
    base_penalties: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ImageScoreResult:
    source_type: str
    source_id: str
    original_url: str
    total: float
    grade: str
    rank: int = 0
    relevance_rank: int = 0
    sort_order: int = 0
    origin: str = "article_body"
    caption: str | None = None
    verdict: str | None = None
    breakdown: dict[str, Any] | None = None
    local_path: str | None = None
    width: int = 0
    height: int = 0
    is_animated: bool = False

    def to_dict(self) -> dict[str, Any]:
        dims = (self.breakdown or {}).get("dimensions") or {}
        cover_dim = dims.get("cover_fit") or {}
        figure_dim = dims.get("figure_prominence") or {}
        flash_dim = dims.get("flash_fit") or {}
        orientation = "square"
        if self.width > 0 and self.height > 0:
            ratio = self.width / self.height
            if ratio >= 1.25:
                orientation = "landscape"
            elif ratio <= 1.0:
                orientation = "portrait"
        animated = self.is_animated or bool((self.breakdown or {}).get("is_animated"))
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "original_url": self.original_url,
            "local_path": self.local_path,
            "relevance_score": round(self.total, 1),
            "relevance_grade": self.grade,
            "relevance_rank": self.relevance_rank,
            "caption": self.caption,
            "verdict": self.verdict,
            "breakdown": self.breakdown,
            "auto_selected": False,
            "cover_fit_score": cover_dim.get("score"),
            "figure_prominence_score": figure_dim.get("score"),
            "flash_fit_score": flash_dim.get("score"),
            "orientation": orientation,
            "width": self.width or None,
            "height": self.height or None,
            "is_animated": animated,
        }


def load_image_scoring_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _CONFIG_PATH
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def grade_from_total(total: float, cfg: dict[str, Any] | None = None) -> str:
    active = cfg or load_image_scoring_config()
    thresholds = active.get("grades") or {}
    if total >= float(thresholds.get("A", 80)):
        return "A"
    if total >= float(thresholds.get("B", 60)):
        return "B"
    if total >= float(thresholds.get("C", 40)):
        return "C"
    return "D"


def _image_dimensions(local_file: Path | None) -> tuple[int, int]:
    if local_file is None or not local_file.exists():
        return 0, 0
    try:
        from PIL import Image

        with Image.open(local_file) as img:
            return img.size
    except Exception:
        return 0, 0


def is_animation_raster(local_file: Path | None) -> bool:
    """GIF 或多帧动画 WebP（适合短视频动效轨）。"""
    if local_file is None or not local_file.exists():
        return False
    suffix = local_file.suffix.lower()
    if suffix == ".gif":
        return True
    if suffix != ".webp":
        return False
    try:
        from PIL import Image

        with Image.open(local_file) as img:
            n_frames = int(getattr(img, "n_frames", 1) or 1)
            animated = bool(getattr(img, "is_animated", False))
            return animated and n_frames > 1
    except Exception:
        return False


def compute_media_bonuses(
    local_file: Path | None,
    *,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cfg = config or load_image_scoring_config()
    if not is_animation_raster(local_file):
        return []
    bonus_cfg = cfg.get("bonuses") or {}
    pts = float(bonus_cfg.get("animated", 8))
    return [{"reason": "animated", "points": pts, "signal": local_file.suffix.lower() if local_file else ""}]


def prefilter_image(
    image: ScorableImage,
    *,
    local_file: Path | None,
    config: dict[str, Any] | None = None,
) -> PreFilterResult:
    cfg = config or load_image_scoring_config()
    prefilter = cfg.get("prefilter") or {}

    if image.download_status != "ok":
        return PreFilterResult(skip=True)

    path = local_file
    if path is None and image.local_path:
        path = Path(image.local_path)
    if path is None or not path.exists():
        return PreFilterResult(skip=True)

    url_lower = image.original_url.lower()
    path_lower = str(path).lower()
    hints = prefilter.get("bad_url_hints") or []
    for hint in hints:
        token = str(hint).lower()
        if token in url_lower or token in path_lower:
            forced = float(prefilter.get("forced_d_score", 20))
            return PreFilterResult(
                skip_vl=True,
                forced_grade="D",
                forced_score=forced,
                base_penalties=[{"reason": "bad_url_hint", "points": 0, "signal": token}],
            )

    width, height = _image_dimensions(path)
    min_w = int(prefilter.get("min_width", 220))
    min_h = int(prefilter.get("min_height", 140))
    if width and height and (width < min_w or height < min_h):
        forced = float(prefilter.get("forced_d_score", 20))
        return PreFilterResult(
            skip_vl=True,
            forced_grade="D",
            forced_score=forced,
            base_penalties=[{"reason": "too_small", "points": 0, "signal": f"{width}x{height}"}],
        )

    penalties: list[dict[str, Any]] = []
    if width and height:
        ratio = width / max(height, 1)
        if ratio < 0.3 or ratio > 4.0:
            pts = int((cfg.get("penalties") or {}).get("extreme_aspect", 10))
            penalties.append({"reason": "extreme_aspect", "points": pts})

    if prefilter.get("watermark_detect") and path is not None:
        from services.image_watermark_detect import has_likely_watermark

        min_regions = int(prefilter.get("watermark_min_regions", 1))
        if has_likely_watermark(path, min_regions=min_regions):
            pts = int((cfg.get("penalties") or {}).get("watermark", 15))
            penalties.append({"reason": "watermark", "points": pts, "signal": "cv_detect"})

    return PreFilterResult(base_penalties=penalties)


def compute_orientation_adjustments(
    width: int,
    height: int,
    *,
    config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (bonuses, penalties) for landscape/portrait preference."""
    cfg = config or load_image_scoring_config()
    if width <= 0 or height <= 0:
        return [], []

    orient = cfg.get("orientation") or {}
    ratio = width / max(height, 1)
    landscape_min = float(orient.get("landscape_min_ratio", 1.25))
    portrait_max = float(orient.get("portrait_max_ratio", 1.0))

    bonuses: list[dict[str, Any]] = []
    penalties: list[dict[str, Any]] = []
    bonus_cfg = cfg.get("bonuses") or {}
    penalty_cfg = cfg.get("penalties") or {}

    if ratio >= landscape_min:
        pts = float(bonus_cfg.get("landscape", 5))
        bonuses.append({"reason": "landscape", "points": pts, "signal": f"{width}x{height}"})
    elif ratio <= portrait_max:
        pts = float(penalty_cfg.get("portrait", 5))
        penalties.append({"reason": "portrait", "points": pts, "signal": f"{width}x{height}"})

    return bonuses, penalties


def _dimension_score(item: ImageScoreResult, key: str) -> float:
    dims = (item.breakdown or {}).get("dimensions") or {}
    dim = dims.get(key) or {}
    return float(dim.get("score") or 0)


def _landscape_priority(width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        return 0
    ratio = width / height
    if ratio >= 1.25:
        return 2
    if ratio <= 1.0:
        return 0
    return 1


def compute_final_score(
    vl_payload: dict[str, Any],
    *,
    extra_penalties: list[dict[str, Any]] | None = None,
    extra_bonuses: list[dict[str, Any]] | None = None,
    width: int = 0,
    height: int = 0,
    config: dict[str, Any] | None = None,
) -> ImageScoreResult:
    cfg = config or load_image_scoring_config()
    weights = cfg.get("weights") or {}

    if vl_payload.get("reject"):
        total = float((cfg.get("prefilter") or {}).get("forced_d_score", 20))
        grade = "D"
        breakdown = {
            "dimensions": vl_payload.get("dimensions") or {},
            "penalties": vl_payload.get("penalties") or [],
            "reject": True,
            "reject_reason": vl_payload.get("reject_reason"),
        }
        return ImageScoreResult(
            source_type="",
            source_id=str(vl_payload.get("source_id") or ""),
            original_url="",
            total=total,
            grade=grade,
            caption=vl_payload.get("caption"),
            verdict=vl_payload.get("verdict"),
            breakdown=breakdown,
        )

    dimensions = vl_payload.get("dimensions") or {}
    weighted_sum = 0.0
    for key in _DIMENSION_KEYS:
        dim = dimensions.get(key) or {}
        score = float(dim.get("score") or 0)
        weight = float(weights.get(key, 0))
        weighted_sum += score * weight * 10

    orient_bonuses, orient_penalties = compute_orientation_adjustments(
        width, height, config=cfg
    )
    bonus_total = 0.0
    all_bonuses: list[dict[str, Any]] = []
    for item in list(extra_bonuses or []) + orient_bonuses:
        pts = float(item.get("points") or 0)
        bonus_total += pts
        all_bonuses.append({**item, "points": pts})

    penalty_total = 0.0
    all_penalties: list[dict[str, Any]] = []
    penalty_cfg = cfg.get("penalties") or {}
    for item in (
        list(vl_payload.get("penalties") or [])
        + list(extra_penalties or [])
        + orient_penalties
    ):
        reason = str(item.get("reason") or "")
        points = item.get("points")
        if points is None and reason in penalty_cfg:
            points = penalty_cfg[reason]
        pts = float(points or 0)
        penalty_total += pts
        all_penalties.append({**item, "points": pts})

    total = max(0.0, min(100.0, round(weighted_sum + bonus_total - penalty_total, 1)))
    grade = grade_from_total(total, cfg)
    breakdown = {
        "dimensions": dimensions,
        "bonuses": all_bonuses,
        "penalties": all_penalties,
        "weighted_sum": round(weighted_sum, 2),
        "width": width,
        "height": height,
        "is_animated": any(b.get("reason") == "animated" for b in all_bonuses),
    }
    return ImageScoreResult(
        source_type="",
        source_id=str(vl_payload.get("source_id") or ""),
        original_url="",
        total=total,
        grade=grade,
        caption=vl_payload.get("caption"),
        verdict=vl_payload.get("verdict"),
        breakdown=breakdown,
        width=width,
        height=height,
    )


def _grade_priority(grade: str) -> int:
    return {"A": 4, "B": 3, "C": 2, "D": 1}.get(grade, 0)


def _source_priority(source_type: str) -> int:
    return 2 if source_type == "article_image" else 1


def _origin_priority(origin: str) -> int:
    if origin == "cover":
        return 2
    if origin == "story_related":
        return 1
    return 0


def _is_animated_item(item: ImageScoreResult) -> bool:
    if item.is_animated:
        return True
    if (item.breakdown or {}).get("is_animated"):
        return True
    bonuses = (item.breakdown or {}).get("bonuses") or []
    return any(b.get("reason") == "animated" for b in bonuses)


def rank_evaluations(items: list[ImageScoreResult]) -> list[ImageScoreResult]:
    ordered = sorted(
        items,
        key=lambda e: (
            -e.total,
            -_grade_priority(e.grade),
            -int(_is_animated_item(e)),
            -_dimension_score(e, "flash_fit"),
            -_dimension_score(e, "figure_prominence"),
            -_landscape_priority(e.width, e.height),
            -_dimension_score(e, "topic_relevance"),
            -_source_priority(e.source_type),
            -_origin_priority(e.origin),
            e.sort_order,
        ),
    )
    for idx, item in enumerate(ordered, start=1):
        item.relevance_rank = idx
        item.rank = idx
    return ordered


def pick_auto_selected(
    evaluations: list[ImageScoreResult],
    *,
    config: dict[str, Any] | None = None,
) -> list[ImageScoreResult]:
    cfg = config or load_image_scoring_config()
    auto = cfg.get("auto_select") or {}
    max_count = int(auto.get("max_count", 6))
    min_count = int(auto.get("min_count", 0))
    min_grade = str(auto.get("min_grade", "A"))
    fallback = str(auto.get("fallback_grade", "B"))
    supplement_grade = str(auto.get("supplement_grade", "C"))

    ranked = rank_evaluations(list(evaluations))
    picked: list[ImageScoreResult] = []
    for grade in (min_grade, fallback):
        tier = [e for e in ranked if e.grade == grade]
        if tier:
            picked = tier[:max_count]
            break

    if min_count > 0 and len(picked) < min_count:
        picked_keys = {(item.source_type, item.source_id) for item in picked}
        for item in ranked:
            if item.grade != supplement_grade:
                continue
            key = (item.source_type, item.source_id)
            if key in picked_keys:
                continue
            picked.append(item)
            picked_keys.add(key)
            if len(picked) >= min(min_count, max_count):
                break

    return picked[:max_count]
