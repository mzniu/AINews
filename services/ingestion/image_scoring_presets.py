"""Image scoring presets and weight helpers for配图相关度评估."""
from __future__ import annotations

from typing import Any

from services.ingestion.image_scorer import DIMENSION_KEYS, DIMENSION_LABELS

DEFAULT_WEIGHTS: dict[str, float] = {
    "topic_relevance": 0.30,
    "info_value": 0.18,
    "visual_quality": 0.12,
    "flash_fit": 0.18,
    "cover_fit": 0.05,
    "figure_prominence": 0.10,
    "compliance": 0.07,
}

DEFAULT_GRADES: dict[str, float] = {"A": 80, "B": 60, "C": 40}

DIMENSION_HINTS: dict[str, str] = {
    "topic_relevance": "图中主体/场景与文章标题、摘要、关键词的匹配程度",
    "info_value": "产品截图、数据图表、现场图优于纯装饰图",
    "visual_quality": "清晰度、分辨率、图中文字可读性",
    "flash_fit": "是否适合 2–3 秒一镜的主画面（非标题卡/过渡图）",
    "cover_fit": "缩略图与传播封面的参考价值（权重通常较低）",
    "figure_prominence": "重要/争议人物是否清晰出镜",
    "compliance": "水印、二维码、广告条、纯 logo 等风险",
}

IMAGE_SCORING_PRESETS: dict[str, dict[str, Any]] = {
    "short_video_clip": {
        "label": "短视频主画面（默认）",
        "description": "优先主题相关与主画面适配，适合 8–12 秒快讯短片",
        "weights": dict(DEFAULT_WEIGHTS),
        "grades": dict(DEFAULT_GRADES),
    },
    "topic_first": {
        "label": "主题优先",
        "description": "强化与文章主题的匹配，适合强叙事、单事件报道",
        "weights": {
            "topic_relevance": 0.38,
            "info_value": 0.16,
            "visual_quality": 0.10,
            "flash_fit": 0.16,
            "cover_fit": 0.04,
            "figure_prominence": 0.08,
            "compliance": 0.08,
        },
        "grades": dict(DEFAULT_GRADES),
    },
    "visual_quality_first": {
        "label": "画质优先",
        "description": "强调清晰度与画面质感，适合产品展示、发布会类素材",
        "weights": {
            "topic_relevance": 0.22,
            "info_value": 0.16,
            "visual_quality": 0.24,
            "flash_fit": 0.14,
            "cover_fit": 0.06,
            "figure_prominence": 0.10,
            "compliance": 0.08,
        },
        "grades": {"A": 78, "B": 58, "C": 38},
    },
    "figure_focus": {
        "label": "人物出镜向",
        "description": "突出人物与名人出镜，适合人物访谈、高管发言类内容",
        "weights": {
            "topic_relevance": 0.24,
            "info_value": 0.14,
            "visual_quality": 0.12,
            "flash_fit": 0.14,
            "cover_fit": 0.05,
            "figure_prominence": 0.26,
            "compliance": 0.05,
        },
        "grades": dict(DEFAULT_GRADES),
    },
    "compliance_strict": {
        "label": "合规严控",
        "description": "提高合规权重，适合对水印/广告更敏感的账号",
        "weights": {
            "topic_relevance": 0.26,
            "info_value": 0.16,
            "visual_quality": 0.12,
            "flash_fit": 0.16,
            "cover_fit": 0.05,
            "figure_prominence": 0.08,
            "compliance": 0.17,
        },
        "grades": {"A": 82, "B": 62, "C": 42},
    },
    "balanced": {
        "label": "均衡探索",
        "description": "七维权重接近均等，适合摸索账号配图偏好",
        "weights": {key: round(1.0 / len(DIMENSION_KEYS), 4) for key in DIMENSION_KEYS},
        "grades": dict(DEFAULT_GRADES),
    },
}


def dimension_catalog() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": DIMENSION_LABELS[key],
            "hint": DIMENSION_HINTS.get(key, ""),
        }
        for key in DIMENSION_KEYS
    ]


def preset_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for preset_id, preset in IMAGE_SCORING_PRESETS.items():
        items.append(
            {
                "id": preset_id,
                "label": preset["label"],
                "description": preset["description"],
                "weights": dict(preset["weights"]),
                "grades": dict(preset.get("grades") or DEFAULT_GRADES),
            }
        )
    return items


def _weights_close(left: dict[str, float], right: dict[str, float], tol: float = 0.008) -> bool:
    for key in DIMENSION_KEYS:
        if abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) > tol:
            return False
    return True


def detect_preset_id(weights: dict[str, Any]) -> str:
    normalized = normalize_weights(weights, strict=False)
    for preset_id, preset in IMAGE_SCORING_PRESETS.items():
        if _weights_close(normalized, preset["weights"]):
            return preset_id
    return "custom"


def normalize_weights(weights: dict[str, Any], *, strict: bool = True) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for key in DIMENSION_KEYS:
        if key not in weights:
            if strict:
                raise ValueError(f"缺少维度权重: {key}")
            cleaned[key] = 0.0
            continue
        value = float(weights[key])
        if value < 0:
            raise ValueError(f"维度 {key} 权重不能为负")
        cleaned[key] = value
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("权重总和必须大于 0")
    return {key: round(cleaned[key] / total, 4) for key in DIMENSION_KEYS}


def validate_grades(grades: dict[str, Any]) -> dict[str, float]:
    ordered = ["A", "B", "C"]
    cleaned: dict[str, float] = {}
    previous = 100.0
    for key in ordered:
        if key not in grades:
            raise ValueError(f"缺少等级分数线: {key}")
        value = float(grades[key])
        if value <= 0 or value >= previous:
            raise ValueError("等级分数线必须满足 A > B > C > 0")
        cleaned[key] = value
        previous = value
    return cleaned


def merge_weights_from_config(cfg: dict[str, Any]) -> dict[str, float]:
    raw = cfg.get("weights") or {}
    if not raw:
        return dict(DEFAULT_WEIGHTS)
    return normalize_weights({key: float(raw.get(key, 0.0)) for key in DIMENSION_KEYS}, strict=False)


def merge_grades_from_config(cfg: dict[str, Any]) -> dict[str, float]:
    raw = cfg.get("grades") or {}
    if not raw:
        return dict(DEFAULT_GRADES)
    return validate_grades(
        {
            "A": float(raw.get("A", DEFAULT_GRADES["A"])),
            "B": float(raw.get("B", DEFAULT_GRADES["B"])),
            "C": float(raw.get("C", DEFAULT_GRADES["C"])),
        }
    )
