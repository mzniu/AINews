"""Staged publish-policy rollout guards: kill-switch, gates, backpressure."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

DEFAULT_KILL_SWITCH = {
    "min_samples": 20,
    "min_median_views": 700,
    "min_completion_rate": 0.30,
}

DEFAULT_STAGE_GATES = {
    "wechat_channels": {
        "min_samples": 20,
        "min_median_views": 1000,
        "min_hit_rate_10k": 0.30,
        "min_completion_rate": 0.34,
        "max_publish_failure_rate": 0.10,
    },
    "douyin": {
        "min_samples": 20,
        "min_median_views": None,
        "protect_baseline": True,
        "max_below_1k_rate": 0.30,
    },
    "kuaishou": {
        "min_samples": 10,
        "require_metrics_match": True,
    },
}

DEFAULT_MAX_QUEUE_DAYS = 2.0


@dataclass(frozen=True)
class KillSwitchDecision:
    platform: str
    should_disable: bool
    reason_code: str
    reasons: tuple[str, ...]
    metrics: Mapping[str, Any]


@dataclass(frozen=True)
class QueueBackpressureDecision:
    stop_new_dispatch: bool
    oldest_age_days: float | None
    max_queue_days: float
    reason_code: str


@dataclass(frozen=True)
class StageGateDecision:
    platform: str
    passed: bool
    reasons: tuple[str, ...]


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _kill_switch_config(config: Mapping[str, Any] | None, platform: str) -> dict[str, Any]:
    policy = (config or {}).get("publish_policy") or {}
    rollout = policy.get("rollout") or {}
    kill = dict(DEFAULT_KILL_SWITCH)
    kill.update(rollout.get("kill_switch") or {})
    platform_cfg = (policy.get("platforms") or {}).get(platform) or {}
    kill.update((platform_cfg.get("kill_switch") or {}).get("thresholds") or {})
    return kill


def evaluate_platform_kill_switch(
    platform: str,
    metrics: Mapping[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
) -> KillSwitchDecision:
    """Disable a platform policy when mature D1 metrics breach stop-loss lines."""
    thresholds = _kill_switch_config(config, platform)
    sample_size = int(metrics.get("sample_size") or 0)
    min_samples = int(thresholds.get("min_samples", 20))
    if sample_size < min_samples:
        return KillSwitchDecision(
            platform=platform,
            should_disable=False,
            reason_code="insufficient_samples",
            reasons=(f"sample_size<{min_samples}",),
            metrics=dict(metrics),
        )

    reasons: list[str] = []
    median_views = _as_float(metrics.get("median_views"))
    min_median = _as_float(thresholds.get("min_median_views"))
    if median_views is not None and min_median is not None and median_views < min_median:
        reasons.append(f"median_views<{min_median}")

    completion = _as_float(metrics.get("completion_rate"))
    min_completion = _as_float(thresholds.get("min_completion_rate"))
    if (
        completion is not None
        and min_completion is not None
        and completion < min_completion
    ):
        reasons.append(f"completion_rate<{min_completion}")

    should_disable = bool(reasons)
    return KillSwitchDecision(
        platform=platform,
        should_disable=should_disable,
        reason_code="stop_loss" if should_disable else "healthy",
        reasons=tuple(reasons) if reasons else ("within_thresholds",),
        metrics=dict(metrics),
    )


def evaluate_queue_backpressure(
    *,
    oldest_pending_at: datetime | None,
    now: datetime | None = None,
    max_queue_days: float = DEFAULT_MAX_QUEUE_DAYS,
) -> QueueBackpressureDecision:
    """Stop new candidate dispatch when the pending queue is older than N days."""
    current = now or datetime.utcnow()
    if oldest_pending_at is None:
        return QueueBackpressureDecision(
            stop_new_dispatch=False,
            oldest_age_days=None,
            max_queue_days=float(max_queue_days),
            reason_code="empty_queue",
        )
    age_days = max(0.0, (current - oldest_pending_at).total_seconds() / 86_400)
    stop = age_days > float(max_queue_days)
    return QueueBackpressureDecision(
        stop_new_dispatch=stop,
        oldest_age_days=age_days,
        max_queue_days=float(max_queue_days),
        reason_code="queue_too_old" if stop else "within_limit",
    )


def platform_kill_switch_active(platform_config: Mapping[str, Any] | None) -> bool:
    if not isinstance(platform_config, Mapping):
        return False
    kill = platform_config.get("kill_switch") or {}
    return bool(kill.get("active"))


def should_dispatch_platform(
    platform: str,
    policy: Mapping[str, Any] | None,
) -> bool:
    """Shadow platforms still dispatch under budgets; killed platforms do not."""
    active = policy or {}
    if not bool(active.get("enabled", False)):
        return False
    platform_config = (active.get("platforms") or {}).get(platform) or {}
    if not isinstance(platform_config, Mapping):
        return False
    if platform_kill_switch_active(platform_config):
        return False
    return True


def platform_mode(platform_config: Mapping[str, Any] | None, *, global_shadow: bool) -> str:
    if not isinstance(platform_config, Mapping):
        return "unknown"
    if platform_kill_switch_active(platform_config):
        return "killed"
    enabled = bool(platform_config.get("enabled", False))
    shadow = bool(global_shadow or platform_config.get("shadow_mode", True))
    if enabled and not shadow:
        return "enforced"
    if shadow:
        return "shadow"
    return "disabled"


def evaluate_stage_gate(
    platform: str,
    metrics: Mapping[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
) -> StageGateDecision:
    """Check whether a platform may be promoted from shadow to enforced."""
    policy = (config or {}).get("publish_policy") or {}
    rollout = policy.get("rollout") or {}
    gates = dict(DEFAULT_STAGE_GATES.get(platform) or {})
    gates.update((rollout.get("stage_gates") or {}).get(platform) or {})

    reasons: list[str] = []
    sample_size = int(metrics.get("sample_size") or 0)
    min_samples = int(gates.get("min_samples") or 0)
    if sample_size < min_samples:
        reasons.append(f"sample_size<{min_samples}")

    checks = (
        ("median_views", "min_median_views", False),
        ("hit_rate_10k", "min_hit_rate_10k", False),
        ("completion_rate", "min_completion_rate", False),
        ("publish_failure_rate", "max_publish_failure_rate", True),
        ("below_1k_rate", "max_below_1k_rate", True),
    )
    for metric_key, threshold_key, is_max in checks:
        threshold = _as_float(gates.get(threshold_key))
        if threshold is None:
            continue
        value = _as_float(metrics.get(metric_key))
        if value is None:
            reasons.append(f"{metric_key}_missing")
            continue
        if is_max and value > threshold:
            reasons.append(f"{metric_key}>{threshold}")
        if not is_max and value < threshold:
            reasons.append(f"{metric_key}<{threshold}")

    return StageGateDecision(
        platform=platform,
        passed=not reasons,
        reasons=tuple(reasons) if reasons else ("ready",),
    )


def apply_platform_kill_switch(
    platform: str,
    *,
    reason: str,
    metrics: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist platform disable + kill_switch metadata; never pause Kuaishou."""
    from services.ingestion.scoring_settings import save_publish_policy_settings

    stamped = (now or datetime.utcnow()).replace(microsecond=0).isoformat()
    payload = {
        "platforms": {
            platform: {
                "enabled": False,
                "kill_switch": {
                    "active": True,
                    "reason": str(reason),
                    "triggered_at": stamped,
                    "metrics": dict(metrics or {}),
                },
            }
        }
    }
    if platform != "kuaishou":
        # Keep explicit non-pause for Kuaishou even when other platforms trip.
        payload["platforms"]["kuaishou"] = {"paused": False}
    return save_publish_policy_settings(payload)


def build_rollout_status(
    *,
    config: Mapping[str, Any],
    candidate_counts: Mapping[str, Mapping[str, int]],
    budget_usage: Mapping[str, Mapping[str, Any]],
    mature_metrics: Mapping[str, Mapping[str, Any]],
    queue: Mapping[str, Any],
    publish_failure_rates: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    policy = config.get("publish_policy") or {}
    global_shadow = bool(policy.get("shadow_mode", True))
    platforms_out: dict[str, Any] = {}
    for platform, platform_config in (policy.get("platforms") or {}).items():
        if not isinstance(platform_config, Mapping):
            continue
        mature = dict(mature_metrics.get(platform) or {})
        d1 = dict(mature.get("24h") or {})
        if publish_failure_rates and platform in publish_failure_rates:
            d1 = {**d1, "publish_failure_rate": publish_failure_rates[platform]}
        gate = evaluate_stage_gate(platform, d1, config=config)
        kill = platform_config.get("kill_switch") or {}
        platforms_out[platform] = {
            "mode": platform_mode(platform_config, global_shadow=global_shadow),
            "enabled": bool(platform_config.get("enabled", False)),
            "shadow_mode": bool(platform_config.get("shadow_mode", True)),
            "paused": bool(platform_config.get("paused", False)),
            "rollout_stage": platform_config.get("rollout_stage"),
            "daily_limit": platform_config.get("daily_limit"),
            "kill_switch": {
                "active": bool(kill.get("active")),
                "reason": kill.get("reason"),
                "triggered_at": kill.get("triggered_at"),
            },
            "candidates": dict(candidate_counts.get(platform) or {}),
            "budget": dict(budget_usage.get(platform) or {}),
            "mature": mature,
            "stage_gate": {
                "passed": gate.passed,
                "reasons": list(gate.reasons),
            },
            "dispatch_allowed": should_dispatch_platform(platform, policy),
        }
    return {
        "policy_version": str(policy.get("policy_version", config.get("policy_version", 1))),
        "enabled": bool(policy.get("enabled", False)),
        "shadow_mode": global_shadow,
        "queue": dict(queue),
        "platforms": platforms_out,
    }


def maybe_apply_kill_switches(
    mature_by_platform: Mapping[str, Mapping[str, Any]],
    *,
    config: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Evaluate and persist kill-switches for enforced platforms that trip stop-loss."""
    policy = (config or {}).get("publish_policy") or {}
    applied: list[dict[str, Any]] = []
    for platform, platform_config in (policy.get("platforms") or {}).items():
        if not isinstance(platform_config, Mapping):
            continue
        if platform_kill_switch_active(platform_config):
            continue
        if platform_mode(platform_config, global_shadow=bool(policy.get("shadow_mode", True))) != "enforced":
            continue
        metrics = (mature_by_platform.get(platform) or {}).get("24h") or {}
        decision = evaluate_platform_kill_switch(platform, metrics, config=config)
        if not decision.should_disable:
            continue
        saved = apply_platform_kill_switch(
            platform,
            reason=";".join(decision.reasons),
            metrics=decision.metrics,
            now=now,
        )
        applied.append(
            {
                "platform": platform,
                "reasons": list(decision.reasons),
                "settings": saved,
            }
        )
    return applied


def collect_rollout_status(session, *, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Assemble rollout observability payload for API/UI."""
    from datetime import timedelta

    from services.ingestion.article_scorer import load_scoring_config
    from services.publishing.metrics.mature_metrics import (
        get_mature_platform_metrics,
        get_pending_queue_stats,
    )
    from src.db.models.publishing import AutoPublishCandidate, PublishJob, PublisherAccount
    from sqlalchemy import func

    active = dict(config or load_scoring_config())
    policy = active.get("publish_policy") or {}
    platforms = list((policy.get("platforms") or {}).keys())
    now = datetime.utcnow()
    published_after = now - timedelta(days=14)
    mature = get_mature_platform_metrics(
        session,
        platforms=platforms or None,
        horizons=(24, 72),
        published_after=published_after,
    )
    queue = get_pending_queue_stats(session, now=now)

    candidate_counts: dict[str, dict[str, int]] = {}
    rows = (
        session.query(
            AutoPublishCandidate.platform,
            AutoPublishCandidate.status,
            func.count(AutoPublishCandidate.id),
        )
        .group_by(AutoPublishCandidate.platform, AutoPublishCandidate.status)
        .all()
    )
    for platform, status, count in rows:
        bucket = candidate_counts.setdefault(str(platform), {})
        bucket[str(status)] = int(count)

    budget_usage: dict[str, dict[str, Any]] = {}
    from zoneinfo import ZoneInfo

    beijing = ZoneInfo("Asia/Shanghai")
    local_today = (
        datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(beijing).date()
    )
    day_start = datetime(
        local_today.year, local_today.month, local_today.day, tzinfo=beijing
    ).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    day_end = day_start + timedelta(days=1)
    for platform, platform_config in (policy.get("platforms") or {}).items():
        used = (
            session.query(func.count(PublishJob.id))
            .join(PublisherAccount, PublishJob.account_id == PublisherAccount.id)
            .filter(
                PublisherAccount.platform == platform,
                PublishJob.status.in_(("pending", "uploading", "published")),
                PublishJob.scheduled_at.isnot(None),
                PublishJob.scheduled_at >= day_start,
                PublishJob.scheduled_at < day_end,
            )
            .scalar()
            or 0
        )
        budget_usage[platform] = {
            "used": int(used),
            "daily_limit": platform_config.get("daily_limit"),
            "date": local_today.isoformat(),
        }

    failure_rates: dict[str, float] = {}
    for platform in platforms:
        total = (
            session.query(func.count(PublishJob.id))
            .join(PublisherAccount, PublishJob.account_id == PublisherAccount.id)
            .filter(
                PublisherAccount.platform == platform,
                PublishJob.created_at >= published_after,
                PublishJob.status.in_(("published", "failed")),
            )
            .scalar()
            or 0
        )
        failed = (
            session.query(func.count(PublishJob.id))
            .join(PublisherAccount, PublishJob.account_id == PublisherAccount.id)
            .filter(
                PublisherAccount.platform == platform,
                PublishJob.created_at >= published_after,
                PublishJob.status == "failed",
            )
            .scalar()
            or 0
        )
        if total:
            failure_rates[platform] = failed / total

    return build_rollout_status(
        config=active,
        candidate_counts=candidate_counts,
        budget_usage=budget_usage,
        mature_metrics=mature,
        queue=queue,
        publish_failure_rates=failure_rates,
    )
