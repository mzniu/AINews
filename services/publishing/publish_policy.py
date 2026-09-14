"""Pure per-platform publishing policy decisions."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

PublishAction = Literal["publish", "defer", "skip"]

_GRADE_RANK = {"D": 1, "C": 2, "B": 3, "A": 4, "S": 5}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


_DEFAULT_POLICY: Mapping[str, Any] = _freeze(
    {
        "policy_version": 1,
        "enabled": False,
        "shadow_mode": True,
        "platforms": {
            "wechat_channels": {
                "enabled": False,
                "shadow_mode": True,
                "thresholds": {
                    "industry_min_grade": "A",
                    "viral_min_grade": "A",
                },
                "weights": {
                    "industry_total": 0.35,
                    "viral_total": 0.35,
                    "motives": {
                        "public_issue": 1.0,
                        "identity": 1.0,
                        "emotional_arousal": 1.0,
                    },
                    "platform_fit_bonus": 10.0,
                },
                "duplicate_penalty": 12.0,
            },
            "douyin": {
                "enabled": False,
                "shadow_mode": True,
                "thresholds": {
                    "industry_min_grade": "A",
                    "viral_min_grade": "B",
                },
                "weights": {
                    "industry_total": 0.35,
                    "viral_total": 0.40,
                    "motives": {
                        "social_currency": 1.0,
                        "emotional_arousal": 1.0,
                    },
                    "platform_fit_bonus": 10.0,
                },
                "duplicate_penalty": 12.0,
            },
            "kuaishou": {
                "enabled": False,
                "shadow_mode": True,
                "thresholds": {
                    "industry_min_grade": "A",
                    "motive_min_score": 6.0,
                },
                "weights": {
                    "industry_total": 0.35,
                    "viral_total": 0.25,
                    "motives": {
                        "identity": 1.5,
                        "social_currency": 1.5,
                    },
                    "platform_fit_bonus": 10.0,
                },
                "duplicate_penalty": 10.0,
            },
        },
    }
)


@dataclass(frozen=True)
class PlatformDecision:
    """Effective publishing action plus its policy explanation."""

    action: PublishAction
    priority: float
    reasons: tuple[str, ...]
    policy_version: str | int
    recommended_action: PublishAction
    shadow_mode: bool


def _grade_meets(grade: str | None, minimum: Any) -> bool:
    current = str(grade or "").strip().upper()
    threshold = str(minimum or "").strip().upper()
    return (
        current in _GRADE_RANK
        and threshold in _GRADE_RANK
        and _GRADE_RANK[current] >= _GRADE_RANK[threshold]
    )


def _bounded_number(value: Any, lower: float, upper: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    if not math.isfinite(number):
        number = lower
    return max(lower, min(upper, number))


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _motive_scores(motives: Any) -> dict[str, float]:
    scores: dict[str, float] = {}
    if isinstance(motives, Mapping):
        items: Iterable[tuple[Any, Any]] = motives.items()
    else:
        normalized: list[tuple[Any, Any]] = []
        for motive in motives or ():
            if isinstance(motive, Mapping):
                normalized.append((motive.get("key"), motive.get("score")))
            else:
                normalized.append(
                    (getattr(motive, "key", None), getattr(motive, "score", None))
                )
        items = normalized

    for key, raw_score in items:
        if isinstance(raw_score, Mapping):
            raw_score = raw_score.get("score")
        elif hasattr(raw_score, "score"):
            raw_score = getattr(raw_score, "score")
        normalized_key = str(key or "").strip()
        if normalized_key:
            scores[normalized_key] = _bounded_number(raw_score, 0.0, 10.0)
    return scores


def _has_platform_fit(platform: str, platform_fit: Any) -> bool:
    if isinstance(platform_fit, str):
        return platform_fit.strip() == platform
    if isinstance(platform_fit, Mapping):
        return bool(platform_fit.get(platform))
    return platform in {str(value).strip() for value in (platform_fit or ())}


def _recommend_action(
    platform: str,
    *,
    industry_grade: str,
    viral_grade: str,
    motives: Mapping[str, float],
    thresholds: Mapping[str, Any],
) -> tuple[PublishAction, str]:
    industry_min = thresholds.get("industry_min_grade", "A")
    industry_passes = _grade_meets(industry_grade, industry_min)

    if platform == "wechat_channels":
        viral_min = thresholds.get("viral_min_grade", "A")
        if industry_passes and _grade_meets(viral_grade, viral_min):
            return "publish", "recommend.publish.wechat_dual_grade"
        return "defer", "recommend.defer.wechat_grade_threshold"

    if platform == "douyin":
        viral_min = thresholds.get("viral_min_grade", "B")
        if industry_passes and _grade_meets(viral_grade, viral_min):
            return "publish", "recommend.publish.douyin_grade_threshold"
        if not _grade_meets(viral_grade, viral_min):
            return "defer", "recommend.defer.douyin_low_viral"
        return "defer", "recommend.defer.douyin_industry_threshold"

    motive_min = _bounded_number(
        thresholds.get("motive_min_score", 6.0),
        0.0,
        10.0,
    )
    identity_or_social = max(
        motives.get("identity", 0.0),
        motives.get("social_currency", 0.0),
    )
    if industry_passes and identity_or_social >= motive_min:
        return "publish", "recommend.publish.kuaishou_industry_motive"
    return "defer", "recommend.defer.kuaishou_continue"


def _priority(
    *,
    industry_total: float,
    viral_total: float,
    motives: Mapping[str, float],
    platform_fitted: bool,
    story_recent_count: int,
    platform_config: Mapping[str, Any],
    reasons: list[str],
) -> float:
    weights = platform_config.get("weights") or {}
    motive_weights = weights.get("motives") or {}
    value = _number(industry_total) * _bounded_number(
        weights.get("industry_total", 0.0), 0.0, 1.0
    )
    value += _number(viral_total) * _bounded_number(
        weights.get("viral_total", 0.0), 0.0, 1.0
    )
    for motive, raw_weight in motive_weights.items():
        value += motives.get(str(motive), 0.0) * _bounded_number(
            raw_weight, 0.0, 10.0
        )

    if platform_fitted:
        value += _bounded_number(weights.get("platform_fit_bonus", 0.0), 0.0, 100.0)
        reasons.append("priority.platform_fit")

    try:
        recent_count = max(0, int(story_recent_count))
    except (TypeError, ValueError):
        recent_count = 0
    if recent_count > 0:
        penalty = _bounded_number(
            platform_config.get("duplicate_penalty", 0.0),
            0.0,
            100.0,
        )
        value -= penalty
        reasons.append(f"priority.recent_story_penalty:{recent_count}")

    return round(max(0.0, min(100.0, value)), 2)


def decide_platform_publish(
    platform: str,
    industry_grade: str,
    industry_total: float,
    viral_grade: str,
    viral_total: float,
    motives: Any,
    platform_fit: Any,
    story_recent_count: int = 0,
    config: dict[str, Any] | None = None,
) -> PlatformDecision:
    """Return a deterministic decision without mutating caller-owned config."""
    if config is None:
        active_config: Mapping[str, Any] = {}
        policy = _DEFAULT_POLICY
    else:
        active_config = config
        policy = active_config.get("publish_policy", active_config)
    policy_version = policy.get(
        "policy_version",
        active_config.get("policy_version", 1),
    )
    normalized_platform = str(platform or "").strip().lower()
    platform_config = (policy.get("platforms") or {}).get(normalized_platform)

    if not isinstance(platform_config, Mapping) or normalized_platform not in {
        "wechat_channels",
        "douyin",
        "kuaishou",
    }:
        return PlatformDecision(
            action="skip",
            priority=0.0,
            reasons=(f"platform.unknown:{normalized_platform or '<empty>'}",),
            policy_version=policy_version,
            recommended_action="skip",
            shadow_mode=False,
        )

    motive_scores = _motive_scores(motives)
    thresholds = platform_config.get("thresholds") or {}
    recommended_action, recommendation_reason = _recommend_action(
        normalized_platform,
        industry_grade=industry_grade,
        viral_grade=viral_grade,
        motives=motive_scores,
        thresholds=thresholds,
    )
    reasons = [recommendation_reason]
    priority = _priority(
        industry_total=industry_total,
        viral_total=viral_total,
        motives=motive_scores,
        platform_fitted=_has_platform_fit(normalized_platform, platform_fit),
        story_recent_count=story_recent_count,
        platform_config=platform_config,
        reasons=reasons,
    )

    global_enabled = bool(policy.get("enabled", False))
    platform_enabled = bool(platform_config.get("enabled", False))
    shadow_mode = bool(
        policy.get("shadow_mode", True)
        or platform_config.get("shadow_mode", True)
    )
    if not global_enabled:
        reasons.append("policy.disabled.global")
    if not platform_enabled:
        reasons.append("policy.disabled.platform")
    if shadow_mode:
        reasons.append("policy.shadow_mode")

    enforced = global_enabled and platform_enabled and not shadow_mode
    effective_action: PublishAction = recommended_action if enforced else "publish"
    return PlatformDecision(
        action=effective_action,
        priority=priority,
        reasons=tuple(reasons),
        policy_version=policy_version,
        recommended_action=recommended_action,
        shadow_mode=shadow_mode,
    )
