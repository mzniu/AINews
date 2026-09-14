from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import services.publishing.rollout_guard as rollout_guard


def test_kill_switch_triggers_after_enough_weak_wechat_samples():
    decision = rollout_guard.evaluate_platform_kill_switch(
        "wechat_channels",
        {
            "sample_size": 20,
            "median_views": 650,
            "completion_rate": 0.28,
        },
    )
    assert decision.should_disable is True
    assert decision.platform == "wechat_channels"
    assert "median_views" in decision.reasons[0] or "completion" in "".join(decision.reasons)


def test_kill_switch_waits_for_minimum_sample_size():
    decision = rollout_guard.evaluate_platform_kill_switch(
        "wechat_channels",
        {
            "sample_size": 19,
            "median_views": 100,
            "completion_rate": 0.10,
        },
    )
    assert decision.should_disable is False
    assert decision.reason_code == "insufficient_samples"


def test_kill_switch_ignores_healthy_metrics():
    decision = rollout_guard.evaluate_platform_kill_switch(
        "wechat_channels",
        {
            "sample_size": 25,
            "median_views": 1200,
            "completion_rate": 0.36,
        },
    )
    assert decision.should_disable is False


def test_queue_backpressure_stops_new_dispatch_after_two_days():
    now = datetime(2026, 9, 13, 8, 0, 0)
    oldest = now - timedelta(days=2, hours=1)
    decision = rollout_guard.evaluate_queue_backpressure(
        oldest_pending_at=oldest,
        now=now,
        max_queue_days=2,
    )
    assert decision.stop_new_dispatch is True
    assert decision.oldest_age_days == pytest.approx(2 + 1 / 24, rel=1e-3)


def test_queue_backpressure_allows_fresh_queue():
    now = datetime(2026, 9, 13, 8, 0, 0)
    decision = rollout_guard.evaluate_queue_backpressure(
        oldest_pending_at=now - timedelta(hours=12),
        now=now,
        max_queue_days=2,
    )
    assert decision.stop_new_dispatch is False


def test_platform_dispatch_skips_killed_platforms_but_not_shadow():
    policy = {
        "enabled": True,
        "shadow_mode": False,
        "platforms": {
            "wechat_channels": {
                "enabled": True,
                "shadow_mode": False,
                "kill_switch": {"active": True, "reason": "weak_d1"},
            },
            "douyin": {
                "enabled": False,
                "shadow_mode": True,
            },
            "kuaishou": {
                "enabled": False,
                "shadow_mode": True,
                "paused": False,
            },
        },
    }
    assert rollout_guard.should_dispatch_platform("wechat_channels", policy) is False
    assert rollout_guard.should_dispatch_platform("douyin", policy) is True
    assert rollout_guard.should_dispatch_platform("kuaishou", policy) is True


def test_wechat_promotion_gate_requires_all_thresholds():
    ready = rollout_guard.evaluate_stage_gate(
        "wechat_channels",
        {
            "sample_size": 20,
            "median_views": 1000,
            "hit_rate_10k": 0.30,
            "completion_rate": 0.34,
            "publish_failure_rate": 0.09,
        },
    )
    assert ready.passed is True

    blocked = rollout_guard.evaluate_stage_gate(
        "wechat_channels",
        {
            "sample_size": 20,
            "median_views": 900,
            "hit_rate_10k": 0.30,
            "completion_rate": 0.34,
            "publish_failure_rate": 0.09,
        },
    )
    assert blocked.passed is False
    assert any("median_views" in reason for reason in blocked.reasons)


def test_apply_kill_switch_persists_platform_flag_without_pausing_kuaishou(tmp_path, monkeypatch):
    local = tmp_path / "article_scoring.local.yaml"
    monkeypatch.setattr(
        "services.ingestion.scoring_settings.SCORING_LOCAL_PATH",
        local,
    )
    monkeypatch.setattr(
        "services.ingestion.scoring_settings.SCORING_BASE_PATH",
        tmp_path / "missing-base.yaml",
    )
    monkeypatch.setattr(
        "services.ingestion.scoring_settings._migrate_legacy_local_config",
        lambda: None,
    )
    local.write_text(
        "publish_policy:\n"
        "  enabled: true\n"
        "  platforms:\n"
        "    wechat_channels:\n"
        "      enabled: true\n"
        "      shadow_mode: false\n"
        "    kuaishou:\n"
        "      paused: false\n",
        encoding="utf-8",
    )

    saved = rollout_guard.apply_platform_kill_switch(
        "wechat_channels",
        reason="d1_median_below_700",
        metrics={"sample_size": 20, "median_views": 500},
        now=datetime(2026, 9, 13, 8, 0, 0),
    )
    assert saved["platforms"]["wechat_channels"]["enabled"] is False
    assert saved["platforms"]["wechat_channels"]["kill_switch"]["active"] is True
    assert saved["platforms"]["kuaishou"]["paused"] is False

    from services.ingestion.scoring_settings import get_publish_policy_settings

    settings = get_publish_policy_settings()
    assert settings["platforms"]["wechat_channels"]["enabled"] is False
    assert settings["platforms"]["wechat_channels"]["kill_switch"]["active"] is True


def test_build_rollout_status_exposes_policy_budget_and_queue_days():
    status = rollout_guard.build_rollout_status(
        config={
            "publish_policy": {
                "policy_version": 1,
                "enabled": True,
                "shadow_mode": False,
                "rollout": {"max_queue_days": 2},
                "platforms": {
                    "wechat_channels": {
                        "enabled": True,
                        "shadow_mode": False,
                        "daily_limit": 8,
                        "rollout_stage": 1,
                    },
                    "douyin": {
                        "enabled": False,
                        "shadow_mode": True,
                        "daily_limit": 10,
                        "rollout_stage": 2,
                    },
                    "kuaishou": {
                        "enabled": False,
                        "shadow_mode": True,
                        "daily_limit": 5,
                        "paused": False,
                        "rollout_stage": 3,
                    },
                },
            }
        },
        candidate_counts={
            "wechat_channels": {"pending": 3, "deferred": 1, "dispatched": 4},
            "douyin": {"pending": 5, "deferred": 0, "dispatched": 2},
            "kuaishou": {"pending": 2, "deferred": 0, "dispatched": 1},
        },
        budget_usage={
            "wechat_channels": {"used": 3, "daily_limit": 8},
            "douyin": {"used": 4, "daily_limit": 10},
            "kuaishou": {"used": 1, "daily_limit": 5},
        },
        mature_metrics={
            "wechat_channels": {
                "24h": {
                    "sample_size": 12,
                    "median_views": 1100,
                    "hit_rate_10k": 0.33,
                    "completion_rate": 0.35,
                }
            }
        },
        queue={"job_count": 40, "oldest_age_days": 1.5, "estimated_days": 1.5},
        publish_failure_rates={"wechat_channels": 0.05},
    )
    assert status["policy_version"] == "1"
    assert status["queue"]["oldest_age_days"] == 1.5
    assert status["platforms"]["wechat_channels"]["mode"] == "enforced"
    assert status["platforms"]["douyin"]["mode"] == "shadow"
    assert status["platforms"]["kuaishou"]["paused"] is False
    assert status["platforms"]["wechat_channels"]["budget"]["used"] == 3
    assert status["platforms"]["wechat_channels"]["candidates"]["pending"] == 3
    assert status["platforms"]["wechat_channels"]["mature"]["24h"]["median_views"] == 1100
