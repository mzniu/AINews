"""Scoring presets and weight helpers for article curation profiles."""
from __future__ import annotations

from typing import Any

from services.ingestion.article_scorer import DIMENSION_LABELS

DIMENSION_KEYS: tuple[str, ...] = tuple(DIMENSION_LABELS.keys())

DEFAULT_WEIGHTS: dict[str, float] = {
    "timeliness": 0.14,
    "prominence": 0.16,
    "event_tension": 0.20,
    "breakthrough": 0.12,
    "product_heat": 0.10,
    "relevance": 0.14,
    "data_signal": 0.04,
    "creatability": 0.04,
    "hot_radar": 0.06,
}

DEFAULT_GRADES: dict[str, float] = {"S": 88, "A": 70, "B": 55, "C": 40}

DIMENSION_HINTS: dict[str, str] = {
    "timeliness": "发布时间越近分数越高，适合追突发",
    "prominence": "名企、名人、二线公司出现在文中",
    "event_tension": "离职、并购、融资、翻车等可传播事件",
    "breakthrough": "首发、融资、开源、SOTA 等突破信号",
    "product_heat": "ChatGPT、Kimi、大模型等产品热词",
    "relevance": "与 AI 垂类关键词的匹配度",
    "data_signal": "浏览量、多源同题等外部数据",
    "creatability": "摘要、正文长度与配图数量",
    "hot_radar": "是否命中 TopHub 热榜及排名",
}

SCORING_PRESETS: dict[str, dict[str, Any]] = {
    "flash_news": {
        "label": "快讯向（默认）",
        "description": "优先时效、名企与可传播事件，适合 AI 快讯自媒体",
        "weights": dict(DEFAULT_WEIGHTS),
        "grades": dict(DEFAULT_GRADES),
    },
    "timeliness_first": {
        "label": "时效优先",
        "description": "强调新鲜度，适合追踪突发与当日热点",
        "weights": {
            "timeliness": 0.28,
            "prominence": 0.16,
            "event_tension": 0.18,
            "breakthrough": 0.10,
            "product_heat": 0.08,
            "relevance": 0.10,
            "data_signal": 0.02,
            "creatability": 0.02,
            "hot_radar": 0.06,
        },
        "grades": dict(DEFAULT_GRADES),
    },
    "product_focus": {
        "label": "产品热点向",
        "description": "侧重产品发布与热词，适合新品跟踪号",
        "weights": {
            "timeliness": 0.10,
            "prominence": 0.12,
            "event_tension": 0.10,
            "breakthrough": 0.22,
            "product_heat": 0.26,
            "relevance": 0.10,
            "data_signal": 0.04,
            "creatability": 0.04,
            "hot_radar": 0.02,
        },
        "grades": {"S": 82, "A": 68, "B": 52, "C": 38},
    },
    "viral_spread": {
        "label": "传播向",
        "description": "强化事件张力与数据信号，适合追热度传播",
        "weights": {
            "timeliness": 0.12,
            "prominence": 0.14,
            "event_tension": 0.24,
            "breakthrough": 0.10,
            "product_heat": 0.08,
            "relevance": 0.08,
            "data_signal": 0.08,
            "creatability": 0.02,
            "hot_radar": 0.14,
        },
        "grades": {"S": 80, "A": 65, "B": 50, "C": 35},
    },
    "depth_creator": {
        "label": "创作向",
        "description": "重视可创作性与话题深度，适合解读、盘点类账号",
        "weights": {
            "timeliness": 0.08,
            "prominence": 0.10,
            "event_tension": 0.10,
            "breakthrough": 0.12,
            "product_heat": 0.08,
            "relevance": 0.20,
            "data_signal": 0.04,
            "creatability": 0.22,
            "hot_radar": 0.06,
        },
        "grades": {"S": 88, "A": 72, "B": 58, "C": 42},
    },
    "balanced": {
        "label": "均衡探索",
        "description": "各维权重接近均等，适合摸索账号定位阶段",
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
    for preset_id, preset in SCORING_PRESETS.items():
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
    for preset_id, preset in SCORING_PRESETS.items():
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
    if strict and abs(total - 1.0) > 0.02:
        pass
    return {key: round(cleaned[key] / total, 4) for key in DIMENSION_KEYS}


def validate_grades(grades: dict[str, Any]) -> dict[str, float]:
    ordered = ["S", "A", "B", "C"]
    cleaned: dict[str, float] = {}
    previous = 100.0
    for key in ordered:
        if key not in grades:
            raise ValueError(f"缺少等级分数线: {key}")
        value = float(grades[key])
        if value <= 0 or value >= previous:
            raise ValueError("等级分数线必须满足 S > A > B > C > 0")
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
            "S": float(raw.get("S", DEFAULT_GRADES["S"])),
            "A": float(raw.get("A", DEFAULT_GRADES["A"])),
            "B": float(raw.get("B", DEFAULT_GRADES["B"])),
            "C": float(raw.get("C", DEFAULT_GRADES["C"])),
        }
    )
