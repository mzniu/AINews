"""Tests for deterministic per-platform publish policy decisions."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from services.publishing.publish_policy import PlatformDecision, decide_platform_publish


def _config(
    *,
    policy_enabled: bool = True,
    policy_shadow: bool = False,
    platform_enabled: bool = True,
    platform_shadow: bool = False,
) -> dict:
    platform_settings = {
        "enabled": platform_enabled,
        "shadow_mode": platform_shadow,
        "thresholds": {
            "industry_min_grade": "A",
            "viral_min_grade": "A",
            "motive_min_score": 6.0,
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
    }
    douyin = copy.deepcopy(platform_settings)
    douyin["thresholds"]["viral_min_grade"] = "B"
    douyin["weights"]["motives"] = {
        "social_currency": 1.0,
        "emotional_arousal": 1.0,
    }
    kuaishou = copy.deepcopy(platform_settings)
    kuaishou["weights"]["motives"] = {
        "identity": 1.5,
        "social_currency": 1.5,
    }
    return {
        "publish_policy": {
            "policy_version": "test-v1",
            "enabled": policy_enabled,
            "shadow_mode": policy_shadow,
            "platforms": {
                "wechat_channels": platform_settings,
                "douyin": douyin,
                "kuaishou": kuaishou,
            },
        }
    }


def _decide(platform: str, config: dict, **overrides) -> PlatformDecision:
    values = {
        "industry_grade": "A",
        "industry_total": 75.0,
        "viral_grade": "A",
        "viral_total": 65.0,
        "motives": {
            "social_currency": 7.0,
            "emotional_arousal": 7.0,
            "identity": 7.0,
            "public_issue": 7.0,
        },
        "platform_fit": [platform],
        "config": config,
    }
    values.update(overrides)
    return decide_platform_publish(platform, **values)


@pytest.mark.parametrize("industry_grade", ["S", "A"])
@pytest.mark.parametrize("viral_grade", ["S", "A"])
def test_wechat_recommends_publish_at_dual_a_plus_threshold(
    industry_grade: str,
    viral_grade: str,
) -> None:
    decision = _decide(
        "wechat_channels",
        _config(),
        industry_grade=industry_grade,
        viral_grade=viral_grade,
    )

    assert decision.recommended_action == "publish"
    assert decision.action == "publish"


@pytest.mark.parametrize(
    ("industry_grade", "viral_grade"),
    [("B", "A"), ("A", "B")],
)
def test_wechat_defers_below_either_grade_threshold(
    industry_grade: str,
    viral_grade: str,
) -> None:
    decision = _decide(
        "wechat_channels",
        _config(),
        industry_grade=industry_grade,
        viral_grade=viral_grade,
    )

    assert decision.recommended_action == "defer"
    assert decision.action == "defer"


@pytest.mark.parametrize("viral_grade", ["S", "A", "B"])
def test_douyin_recommends_publish_for_industry_a_plus_and_viral_b_plus(
    viral_grade: str,
) -> None:
    decision = _decide("douyin", _config(), viral_grade=viral_grade)

    assert decision.recommended_action == "publish"


@pytest.mark.parametrize("viral_grade", ["C", "D"])
def test_douyin_defers_viral_c_or_d(viral_grade: str) -> None:
    decision = _decide("douyin", _config(), viral_grade=viral_grade)

    assert decision.recommended_action == "defer"
    assert decision.action == "defer"
    assert any("viral" in reason for reason in decision.reasons)


def test_douyin_defers_when_industry_is_below_a() -> None:
    decision = _decide("douyin", _config(), industry_grade="B", viral_grade="A")

    assert decision.recommended_action == "defer"


@pytest.mark.parametrize("motive", ["identity", "social_currency"])
def test_kuaishou_recommends_publish_for_industry_a_plus_and_motive_six(
    motive: str,
) -> None:
    motives = {"identity": 0.0, "social_currency": 0.0}
    motives[motive] = 6.0

    decision = _decide("kuaishou", _config(), motives=motives)

    assert decision.recommended_action == "publish"


@pytest.mark.parametrize(
    ("industry_grade", "motives"),
    [
        ("B", {"identity": 10.0, "social_currency": 10.0}),
        ("A", {"identity": 5.9, "social_currency": 5.9}),
        ("D", {"identity": 0.0, "social_currency": 0.0}),
    ],
)
def test_kuaishou_never_hard_skips_low_scores(
    industry_grade: str,
    motives: dict[str, float],
) -> None:
    decision = _decide(
        "kuaishou",
        _config(),
        industry_grade=industry_grade,
        viral_grade="D",
        motives=motives,
    )

    assert decision.recommended_action == "defer"
    assert decision.action == "defer"


def test_unknown_platform_safely_skips() -> None:
    decision = _decide("unknown_platform", _config())

    assert decision.action == "skip"
    assert decision.recommended_action == "skip"
    assert any(reason.startswith("platform.unknown") for reason in decision.reasons)


def test_explicit_platform_fit_increases_priority() -> None:
    config = _config()

    fitted = _decide("douyin", config, platform_fit=["douyin"])
    not_fitted = _decide("douyin", config, platform_fit=[])

    assert fitted.priority - not_fitted.priority == pytest.approx(10.0)
    assert "priority.platform_fit" in fitted.reasons


def test_recent_story_applies_configured_priority_penalty_without_skipping() -> None:
    config = _config()

    fresh = _decide("douyin", config)
    repeated = _decide("douyin", config, story_recent_count=3)

    assert repeated.priority == pytest.approx(fresh.priority - 12.0)
    assert repeated.recommended_action == "publish"
    assert any("recent_story" in reason for reason in repeated.reasons)


@pytest.mark.parametrize(
    ("industry_total", "viral_total", "motives", "expected"),
    [
        (-1_000.0, -1_000.0, {"social_currency": -100.0}, 0.0),
        (1_000.0, 1_000.0, {"social_currency": 100.0}, 100.0),
    ],
)
def test_priority_is_bounded_zero_to_one_hundred(
    industry_total: float,
    viral_total: float,
    motives: dict[str, float],
    expected: float,
) -> None:
    decision = _decide(
        "douyin",
        _config(),
        industry_total=industry_total,
        viral_total=viral_total,
        motives=motives,
        platform_fit=[],
    )

    assert decision.priority == expected


@pytest.mark.parametrize(
    ("policy_enabled", "platform_enabled", "expected_reason"),
    [
        (False, True, "policy.disabled.global"),
        (True, False, "policy.disabled.platform"),
    ],
)
def test_disabled_policy_preserves_legacy_publish_behavior(
    policy_enabled: bool,
    platform_enabled: bool,
    expected_reason: str,
) -> None:
    config = _config(
        policy_enabled=policy_enabled,
        platform_enabled=platform_enabled,
    )

    decision = _decide("douyin", config, viral_grade="D")

    assert decision.recommended_action == "defer"
    assert decision.action == "publish"
    assert expected_reason in decision.reasons


@pytest.mark.parametrize(
    ("policy_shadow", "platform_shadow"),
    [(True, False), (False, True)],
)
def test_shadow_mode_preserves_publish_and_exposes_recommendation(
    policy_shadow: bool,
    platform_shadow: bool,
) -> None:
    config = _config(
        policy_shadow=policy_shadow,
        platform_shadow=platform_shadow,
    )

    decision = _decide("douyin", config, viral_grade="D")

    assert decision.shadow_mode is True
    assert decision.recommended_action == "defer"
    assert decision.action == "publish"
    assert "policy.shadow_mode" in decision.reasons


def test_enabled_non_shadow_policy_enforces_recommendation() -> None:
    decision = _decide("douyin", _config(), viral_grade="D")

    assert decision.shadow_mode is False
    assert decision.action == decision.recommended_action == "defer"


def test_decision_does_not_mutate_caller_config() -> None:
    config = _config()
    original = copy.deepcopy(config)

    _decide("wechat_channels", config, story_recent_count=2)

    assert config == original


def test_decision_has_explainable_string_reasons_and_policy_version() -> None:
    decision = _decide("wechat_channels", _config())

    assert isinstance(decision, PlatformDecision)
    assert decision.policy_version == "test-v1"
    assert decision.reasons
    assert all(isinstance(reason, str) and reason for reason in decision.reasons)
    assert any(reason.startswith("recommend.publish") for reason in decision.reasons)


def test_config_none_uses_pure_internal_default(monkeypatch) -> None:
    def fail_if_loaded(*args, **kwargs):
        raise AssertionError("runtime scoring config must not be loaded")

    monkeypatch.setattr(
        "services.ingestion.article_scorer.load_scoring_config",
        fail_if_loaded,
    )
    inputs = {
        "platform": "douyin",
        "industry_grade": "A",
        "industry_total": 75.0,
        "viral_grade": "D",
        "viral_total": 20.0,
        "motives": {"social_currency": 3.0, "emotional_arousal": 2.0},
        "platform_fit": [],
    }

    first = decide_platform_publish(**inputs)
    second = decide_platform_publish(**inputs)

    assert first == second
    assert first.recommended_action == "defer"
    assert first.action == "publish"
    assert first.shadow_mode is True


def test_default_yaml_declares_platform_policy_controls() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "article_scoring.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    policy = config["publish_policy"]
    platforms = policy["platforms"]

    assert policy["enabled"] is False
    assert policy["shadow_mode"] is True
    assert policy["policy_version"]
    assert {
        platform: settings["daily_limit"]
        for platform, settings in platforms.items()
    } == {"wechat_channels": 8, "douyin": 10, "kuaishou": 5}
    assert platforms["wechat_channels"]["thresholds"] == {
        "industry_min_grade": "A",
        "viral_min_grade": "A",
    }
    assert platforms["douyin"]["thresholds"] == {
        "industry_min_grade": "A",
        "viral_min_grade": "B",
    }
    assert platforms["kuaishou"]["thresholds"] == {
        "industry_min_grade": "A",
        "motive_min_score": 6,
    }
    for settings in platforms.values():
        assert settings["enabled"] is False
        assert settings["shadow_mode"] is True
        assert settings["thresholds"]
        assert settings["weights"]
        assert settings["duplicate_penalty"] > 0

    def minutes(value: str) -> int:
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)

    all_slots: list[tuple[str, int]] = []
    for platform, settings in platforms.items():
        start = minutes(settings["window_start"])
        end = minutes(settings["window_end"])
        platform_slots = [minutes(value) for value in settings["slots"]]
        assert all(start <= value <= end for value in platform_slots)
        all_slots.extend((platform, value) for value in platform_slots)
    for index, (left_platform, left_slot) in enumerate(all_slots):
        for right_platform, right_slot in all_slots[index + 1 :]:
            if left_platform != right_platform:
                assert abs(left_slot - right_slot) >= 15
    assert platforms["kuaishou"]["paused"] is False
