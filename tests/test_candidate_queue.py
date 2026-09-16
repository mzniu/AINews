from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

import services.publishing.candidate_queue as candidate_queue
from services.publishing.candidate_queue import (
    dispatch_daily_candidates,
    evaluate_article_candidates,
)
from services.publishing.publish_policy import PlatformDecision
from services.publishing.worker import PublishWorker
from src.db.engine import Base, create_app_engine
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.db.models.publishing import (
    AutoPublishCandidate,
    AutoPublishDispatchLease,
    PublishJob,
    PublisherAccount,
)


def _policy(
    *,
    platforms: tuple[str, ...] = ("douyin",),
    daily_limit: int = 2,
    shadow: bool = False,
    slots: list[str] | None = None,
) -> dict:
    all_platforms = {}
    for platform in platforms:
        all_platforms[platform] = {
            "enabled": True,
            "shadow_mode": shadow,
            "daily_limit": daily_limit,
            "slots": slots or ["09:00", "12:00", "18:00"],
            "thresholds": {
                "industry_min_grade": "A",
                "viral_min_grade": "B",
                "motive_min_score": 6,
            },
            "weights": {
                "industry_total": 0.35,
                "viral_total": 0.40,
                "motives": {
                    "social_currency": 1.0,
                    "emotional_arousal": 1.0,
                    "identity": 1.0,
                },
                "platform_fit_bonus": 10,
            },
            "duplicate_penalty": 12,
        }
    return {
        "publish_policy": {
            "policy_version": "queue-v1",
            "enabled": True,
            "shadow_mode": shadow,
            "platforms": all_platforms,
        },
        "post_score_automation": {
            "auto_publish": {
                "enabled": True,
                "quiet_hours": {
                    "enabled": True,
                    "start": "23:00",
                    "end": "07:00",
                },
            },
            "story_gate": {"enabled": False},
        },
    }


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    engine = create_app_engine(f"sqlite:///{(tmp_path / 'candidates.db').as_posix()}")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    session.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="aitnt_news",
            enabled=True,
            schedule_cron="0 * * * *",
        )
    )
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _seed_video(tmp_path: Path, article_id: str) -> str:
    path = tmp_path / "data" / "videos" / f"{article_id}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"video")
    return f"data/videos/{path.name}"


def _article(
    tmp_path: Path,
    article_id: str,
    *,
    viral_grade: str = "A",
    story_id: str | None = None,
) -> IngestedArticle:
    return IngestedArticle(
        id=article_id,
        source_id="src1",
        canonical_url=f"https://example.com/{article_id}",
        title=f"title-{article_id}",
        score_grade="A",
        score_total=80,
        story_id=story_id,
        generated_video_path=_seed_video(tmp_path, article_id),
        video_draft_json=json.dumps({"main_line1": f"title-{article_id}"}),
        score_breakdown_json=json.dumps(
            {
                "industry": {"grade": "A", "total": 80},
                "viral": {
                    "grade": viral_grade,
                    "total": 70 if viral_grade in {"S", "A", "B"} else 20,
                    "motives": [
                        {"key": "social_currency", "score": 8},
                        {"key": "identity", "score": 7},
                    ],
                    "platform_fit": ["douyin"],
                },
            }
        ),
    )


def _account(session, platform: str) -> PublisherAccount:
    account = PublisherAccount(
        id=f"account-{platform}",
        platform=platform,
        nickname=platform,
        session_path=f"data/publish/sessions/{platform}.json",
        status="active",
    )
    session.add(account)
    session.flush()
    return account


def _candidate(
    session,
    article: IngestedArticle,
    platform: str,
    priority: float,
    *,
    status: str = "pending",
) -> AutoPublishCandidate:
    row = AutoPublishCandidate(
        article_id=article.id,
        platform=platform,
        action="publish",
        recommended_action="publish",
        priority=priority,
        reasons_json="[]",
        policy_version="queue-v1",
        status=status,
        evaluated_at=datetime.utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def test_candidate_model_enforces_article_platform_policy_uniqueness(
    db_session, tmp_path
):
    article = _article(tmp_path, "unique")
    db_session.add(article)
    db_session.flush()
    _candidate(db_session, article, "douyin", 10)
    db_session.add(
        AutoPublishCandidate(
            article_id=article.id,
            platform="douyin",
            action="publish",
            recommended_action="publish",
            priority=11,
            reasons_json="[]",
            policy_version="queue-v1",
            status="pending",
            evaluated_at=datetime.utcnow(),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_evaluate_extracts_breakdown_counts_recent_story_and_upserts_idempotently(
    db_session, tmp_path, monkeypatch
):
    now = datetime.utcnow()
    article = _article(tmp_path, "extract", story_id="story-1")
    recent = _article(tmp_path, "recent", story_id="story-1")
    recent.created_at = now - timedelta(hours=3)
    old = _article(tmp_path, "old", story_id="story-1")
    old.created_at = now - timedelta(hours=25)
    db_session.add_all([article, recent, old])
    db_session.commit()
    captured = {}

    def decide(platform, **kwargs):
        captured.update(kwargs)
        return PlatformDecision(
            action="publish",
            priority=91.5,
            reasons=("recommend.publish.test",),
            policy_version="queue-v1",
            recommended_action="publish",
            shadow_mode=False,
        )

    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )
    monkeypatch.setattr(
        "services.publishing.candidate_queue.decide_platform_publish", decide
    )

    first = evaluate_article_candidates(db_session, article, _policy())
    second = evaluate_article_candidates(db_session, article, _policy())
    db_session.flush()

    assert len(first["candidates"]) == len(second["candidates"]) == 1
    assert db_session.query(AutoPublishCandidate).count() == 1
    row = db_session.query(AutoPublishCandidate).one()
    assert row.status == "pending"
    assert row.priority == pytest.approx(91.5)
    assert captured["industry_grade"] == "A"
    assert captured["industry_total"] == 80
    assert captured["viral_grade"] == "A"
    assert captured["viral_total"] == 70
    assert captured["motives"][0]["key"] == "social_currency"
    assert captured["platform_fit"] == ["douyin"]
    assert captured["story_recent_count"] == 1


def test_shadow_publish_preserves_defer_recommendation(db_session, tmp_path, monkeypatch):
    article = _article(tmp_path, "shadow", viral_grade="D")
    db_session.add(article)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )

    evaluate_article_candidates(
        db_session, article, _policy(shadow=True)
    )
    row = db_session.query(AutoPublishCandidate).one()

    assert row.action == "publish"
    assert row.recommended_action == "defer"
    assert row.status == "pending"
    assert "policy.shadow_mode" in json.loads(row.reasons_json)


def test_effective_defer_and_skip_are_audit_records(db_session, tmp_path, monkeypatch):
    article = _article(tmp_path, "defer", viral_grade="D")
    db_session.add(article)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )

    evaluate_article_candidates(db_session, article, _policy())
    deferred = db_session.query(AutoPublishCandidate).one()
    assert deferred.status == "deferred"

    skipped_article = _article(tmp_path, "skip")
    db_session.add(skipped_article)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.decide_platform_publish",
        lambda *args, **kwargs: PlatformDecision(
            action="skip",
            priority=0,
            reasons=("test.skip",),
            policy_version="queue-v1",
            recommended_action="skip",
            shadow_mode=False,
        ),
    )
    evaluate_article_candidates(db_session, skipped_article, _policy())
    skipped = (
        db_session.query(AutoPublishCandidate)
        .filter_by(article_id=skipped_article.id)
        .one()
    )
    assert skipped.status == "skipped"


def test_deferred_candidate_reevaluates_only_after_48_hours(
    db_session, tmp_path, monkeypatch
):
    article = _article(tmp_path, "retry", viral_grade="D")
    db_session.add(article)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )
    evaluate_article_candidates(db_session, article, _policy())
    row = db_session.query(AutoPublishCandidate).one()
    original_evaluated_at = row.evaluated_at
    calls = 0

    def publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        return PlatformDecision(
            action="publish",
            priority=99,
            reasons=("reevaluated",),
            policy_version="queue-v1",
            recommended_action="publish",
            shadow_mode=False,
        )

    monkeypatch.setattr(
        "services.publishing.candidate_queue.decide_platform_publish", publish
    )
    evaluate_article_candidates(db_session, article, _policy())
    assert calls == 0
    assert row.evaluated_at == original_evaluated_at

    row.evaluated_at = datetime.utcnow() - timedelta(hours=49)
    db_session.flush()
    evaluate_article_candidates(db_session, article, _policy())
    assert calls == 1
    assert row.status == "pending"
    assert row.priority == 99


def test_dispatch_selects_top_k_with_remaining_budget_and_is_repeat_safe(
    db_session, tmp_path
):
    cfg = _policy(daily_limit=2)
    _account(db_session, "douyin")
    articles = [_article(tmp_path, f"rank-{n}") for n in range(3)]
    db_session.add_all(articles)
    db_session.flush()
    rows = [
        _candidate(db_session, articles[0], "douyin", 10),
        _candidate(db_session, articles[1], "douyin", 90),
        _candidate(db_session, articles[2], "douyin", 50),
    ]
    db_session.commit()
    now = datetime(2026, 9, 13, 0, 0)  # 08:00 Beijing

    result = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()
    again = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()

    assert [item["article_id"] for item in result["dispatched"]] == [
        articles[1].id,
        articles[2].id,
    ]
    assert again["dispatched"] == []
    assert db_session.query(PublishJob).count() == 2
    assert rows[0].status == "pending"
    assert rows[1].status == rows[2].status == "dispatched"
    assert rows[1].publish_job_id and rows[2].publish_job_id


def test_dispatch_creates_one_job_for_each_selected_platform(db_session, tmp_path):
    cfg = _policy(platforms=("douyin", "kuaishou"), daily_limit=1)
    article = _article(tmp_path, "multi-platform")
    db_session.add(article)
    _account(db_session, "douyin")
    _account(db_session, "kuaishou")
    db_session.flush()
    dy = _candidate(db_session, article, "douyin", 90)
    ks = _candidate(db_session, article, "kuaishou", 80)
    db_session.commit()

    result = dispatch_daily_candidates(
        db_session, now=datetime(2026, 9, 13, 0, 0), config=cfg
    )
    db_session.commit()

    assert len(result["dispatched"]) == 2
    jobs = db_session.query(PublishJob).all()
    assert len(jobs) == 2
    assert {job.account_id for job in jobs} == {
        "account-douyin",
        "account-kuaishou",
    }
    assert dy.publish_job_id != ks.publish_job_id


def test_dispatch_preserves_effective_publish_when_platform_policy_is_disabled(
    db_session, tmp_path, monkeypatch
):
    cfg = _policy(daily_limit=1)
    cfg["publish_policy"]["platforms"]["douyin"]["enabled"] = False
    article = _article(tmp_path, "platform-disabled", viral_grade="D")
    db_session.add(article)
    _account(db_session, "douyin")
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )
    evaluate_article_candidates(db_session, article, cfg)
    candidate = db_session.query(AutoPublishCandidate).one()
    assert candidate.action == "publish"
    assert candidate.status == "pending"

    result = dispatch_daily_candidates(
        db_session, now=datetime(2026, 9, 13, 0, 0), config=cfg
    )

    assert len(result["dispatched"]) == 1
    assert candidate.status == "dispatched"


def test_dispatch_failure_rolls_back_partial_job_and_defers_candidate(
    db_session, tmp_path, monkeypatch
):
    cfg = _policy(daily_limit=1)
    article = _article(tmp_path, "failure")
    db_session.add(article)
    account = _account(db_session, "douyin")
    db_session.flush()
    candidate = _candidate(db_session, article, "douyin", 90)
    db_session.commit()

    def fail_after_flush(session, *, article, account, scheduled_at):
        session.add(
            PublishJob(
                account_id=account.id,
                video_path=article.generated_video_path,
                title="partial",
                status="pending",
                source_type="ingestion",
                source_id=article.id,
                scheduled_at=scheduled_at,
            )
        )
        session.flush()
        raise ValueError("compliance failure")

    monkeypatch.setattr(
        "services.publishing.candidate_queue.create_ingestion_publish_job",
        fail_after_flush,
    )

    dispatch_now = datetime(2026, 9, 13, 0, 0)
    result = dispatch_daily_candidates(
        db_session, now=dispatch_now, config=cfg
    )
    db_session.commit()

    assert result["dispatched"] == []
    assert db_session.query(PublishJob).count() == 0
    assert candidate.status == "deferred"
    assert candidate.evaluated_at == dispatch_now
    assert "dispatch.failed" in json.loads(candidate.reasons_json)[-1]


def test_dispatch_leaves_overflow_pending_for_a_later_day(db_session, tmp_path):
    cfg = _policy(daily_limit=2, slots=["09:00"])
    _account(db_session, "douyin")
    articles = [_article(tmp_path, f"overflow-{n}") for n in range(2)]
    db_session.add_all(articles)
    db_session.flush()
    candidates = [
        _candidate(db_session, articles[0], "douyin", 90),
        _candidate(db_session, articles[1], "douyin", 80),
    ]
    db_session.commit()

    first = dispatch_daily_candidates(
        db_session, now=datetime(2026, 9, 13, 0, 0), config=cfg
    )
    db_session.commit()
    second = dispatch_daily_candidates(
        db_session, now=datetime(2026, 9, 14, 0, 0), config=cfg
    )
    db_session.commit()

    assert len(first["dispatched"]) == 1
    assert len(second["dispatched"]) == 1
    assert all(row.status == "dispatched" for row in candidates)


def test_worker_registers_single_candidate_dispatcher_only_when_policy_enabled(
    monkeypatch,
):
    worker = PublishWorker(embedded=True)
    worker._register_candidate_dispatch_job(_policy())
    worker._register_candidate_dispatch_job(_policy())
    assert [job.id for job in worker.scheduler.get_jobs()].count(
        "dispatch_publish_candidates"
    ) == 1

    disabled = PublishWorker(embedded=True)
    disabled._register_candidate_dispatch_job(
        {"publish_policy": {"enabled": False}}
    )
    assert "dispatch_publish_candidates" not in {
        job.id for job in disabled.scheduler.get_jobs()
    }


def test_dispatch_automatically_reevaluates_only_due_deferred_candidates(
    db_session, tmp_path, monkeypatch
):
    cfg = _policy(daily_limit=2)
    now = datetime(2026, 9, 13, 0, 0)
    _account(db_session, "douyin")
    due_article = _article(tmp_path, "due-reevaluate", viral_grade="A")
    fresh_article = _article(tmp_path, "fresh-defer", viral_grade="A")
    db_session.add_all([due_article, fresh_article])
    db_session.flush()
    due = _candidate(
        db_session, due_article, "douyin", 10, status="deferred"
    )
    fresh = _candidate(
        db_session, fresh_article, "douyin", 10, status="deferred"
    )
    due.action = due.recommended_action = "defer"
    fresh.action = fresh.recommended_action = "defer"
    due.evaluated_at = now - timedelta(hours=49)
    fresh.evaluated_at = now - timedelta(hours=47)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )

    result = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()

    assert [item["article_id"] for item in result["dispatched"]] == [
        due_article.id
    ]
    assert due.status == "dispatched"
    assert due.evaluated_at == now
    assert fresh.status == "deferred"
    assert fresh.evaluated_at == now - timedelta(hours=47)
    assert (
        db_session.query(PublishJob)
        .filter_by(source_id=fresh_article.id)
        .count()
        == 0
    )


def test_due_deferred_candidate_uses_new_policy_version_without_overwriting_audit(
    db_session, tmp_path, monkeypatch
):
    cfg = _policy(daily_limit=1)
    cfg["publish_policy"]["policy_version"] = "queue-v2"
    now = datetime(2026, 9, 13, 0, 0)
    article = _article(tmp_path, "version-bump", viral_grade="A")
    db_session.add(article)
    _account(db_session, "douyin")
    db_session.flush()
    old = _candidate(
        db_session, article, "douyin", 10, status="deferred"
    )
    old.action = old.recommended_action = "defer"
    old.evaluated_at = now - timedelta(hours=49)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )

    result = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()

    rows = (
        db_session.query(AutoPublishCandidate)
        .filter_by(article_id=article.id)
        .order_by(AutoPublishCandidate.policy_version)
        .all()
    )
    assert len(result["dispatched"]) == 1
    assert [(row.policy_version, row.status) for row in rows] == [
        ("queue-v1", "deferred"),
        ("queue-v2", "dispatched"),
    ]


def test_atomic_candidate_claim_allows_only_one_sqlite_session_to_create_job(
    db_session, tmp_path
):
    from sqlalchemy.orm import sessionmaker

    cfg = _policy(daily_limit=1)
    article = _article(tmp_path, "atomic-claim")
    db_session.add(article)
    account = _account(db_session, "douyin")
    candidate = _candidate(db_session, article, "douyin", 90)
    db_session.commit()
    factory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    first = factory()
    second = factory()
    try:
        first_won = candidate_queue._claim_candidate(first, candidate.id)
        first.commit()
        second_won = candidate_queue._claim_candidate(second, candidate.id)
        second.commit()
        assert [first_won, second_won] == [True, False]

        for won, session in ((first_won, first), (second_won, second)):
            if not won:
                continue
            create = candidate_queue.create_ingestion_publish_job(
                session,
                article=session.get(IngestedArticle, article.id),
                account=session.get(PublisherAccount, account.id),
                scheduled_at=datetime(2026, 9, 13, 1, 0),
            )
            claimed = session.get(AutoPublishCandidate, candidate.id)
            claimed.status = "dispatched"
            claimed.publish_job_id = create.id
            session.commit()
    finally:
        first.close()
        second.close()

    db_session.expire_all()
    assert db_session.query(PublishJob).count() == 1
    assert db_session.get(AutoPublishCandidate, candidate.id).status == "dispatched"


@pytest.mark.parametrize("job_state", ["failed", "cancelled", "missing"])
def test_dispatch_reconciles_broken_terminal_candidate(
    db_session, tmp_path, job_state
):
    cfg = _policy(daily_limit=1)
    article = _article(tmp_path, f"reconcile-{job_state}")
    db_session.add(article)
    account = _account(db_session, "douyin")
    db_session.flush()
    candidate = _candidate(
        db_session, article, "douyin", 90, status="dispatched"
    )
    if job_state == "missing":
        candidate.publish_job_id = None
    else:
        old_job = PublishJob(
            id=f"old-{job_state}",
            account_id=account.id,
            video_path=article.generated_video_path,
            title="old",
            status=job_state,
            source_type="ingestion",
            source_id=article.id,
            scheduled_at=datetime(2026, 9, 12, 1, 0),
        )
        db_session.add(old_job)
        db_session.flush()
        candidate.publish_job_id = old_job.id
    db_session.commit()

    result = dispatch_daily_candidates(
        db_session, now=datetime(2026, 9, 13, 0, 0), config=cfg
    )
    db_session.commit()

    assert len(result["dispatched"]) == 1
    assert candidate.status == "dispatched"
    assert candidate.publish_job_id not in {
        None,
        f"old-{job_state}",
    }
    assert any(
        reason.startswith(f"reconcile.{job_state}")
        for reason in json.loads(candidate.reasons_json)
    )


def test_failed_terminal_from_old_policy_is_reevaluated_under_current_version(
    db_session, tmp_path, monkeypatch
):
    cfg = _policy(daily_limit=1)
    cfg["publish_policy"]["policy_version"] = "queue-v2"
    now = datetime(2026, 9, 13, 0, 0)
    article = _article(tmp_path, "old-terminal", viral_grade="A")
    db_session.add(article)
    account = _account(db_session, "douyin")
    db_session.flush()
    old = _candidate(
        db_session, article, "douyin", 90, status="dispatched"
    )
    failed = PublishJob(
        id="old-policy-failed",
        account_id=account.id,
        video_path=article.generated_video_path,
        title="failed",
        status="failed",
        source_type="ingestion",
        source_id=article.id,
    )
    db_session.add(failed)
    db_session.flush()
    old.publish_job_id = failed.id
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )

    result = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()

    rows = (
        db_session.query(AutoPublishCandidate)
        .filter_by(article_id=article.id)
        .order_by(AutoPublishCandidate.policy_version)
        .all()
    )
    assert len(result["dispatched"]) == 1
    assert [(row.policy_version, row.status) for row in rows] == [
        ("queue-v1", "deferred"),
        ("queue-v2", "dispatched"),
    ]


@pytest.mark.parametrize("job_state", ["pending", "uploading", "published"])
def test_dispatch_keeps_healthy_terminal_candidates_terminal(
    db_session, tmp_path, job_state
):
    cfg = _policy(daily_limit=2)
    article = _article(tmp_path, f"terminal-{job_state}")
    db_session.add(article)
    account = _account(db_session, "douyin")
    db_session.flush()
    candidate = _candidate(
        db_session, article, "douyin", 90, status="dispatched"
    )
    job = PublishJob(
        id=f"healthy-{job_state}",
        account_id=account.id,
        video_path=article.generated_video_path,
        title="healthy",
        status=job_state,
        source_type="ingestion",
        source_id=article.id,
        scheduled_at=datetime(2026, 9, 13, 1, 0),
    )
    db_session.add(job)
    db_session.flush()
    candidate.publish_job_id = job.id
    db_session.commit()

    result = dispatch_daily_candidates(
        db_session, now=datetime(2026, 9, 13, 0, 0), config=cfg
    )

    assert result["dispatched"] == []
    assert candidate.status == "dispatched"
    assert candidate.publish_job_id == job.id


def test_active_dispatch_lease_blocks_and_expired_lease_recovers(
    db_session, tmp_path
):
    cfg = _policy(daily_limit=1)
    now = datetime(2026, 9, 13, 0, 0)
    article = _article(tmp_path, "lease-recovery")
    db_session.add(article)
    _account(db_session, "douyin")
    db_session.flush()
    _candidate(db_session, article, "douyin", 90)
    lease = AutoPublishDispatchLease(
        platform="douyin",
        dispatch_date=date(2026, 9, 13),
        owner_id="other-process",
        acquired_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    db_session.add(lease)
    db_session.commit()

    blocked = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()
    assert blocked["dispatched"] == []
    assert db_session.query(PublishJob).count() == 0

    lease.expires_at = now - timedelta(seconds=1)
    db_session.commit()
    recovered = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()

    assert len(recovered["dispatched"]) == 1
    assert db_session.query(PublishJob).count() == 1
    assert db_session.query(AutoPublishDispatchLease).count() == 0


def test_concurrent_full_dispatch_respects_one_platform_daily_budget(
    db_session, tmp_path, monkeypatch
):
    from sqlalchemy.orm import sessionmaker

    cfg = _policy(daily_limit=1)
    now = datetime(2026, 9, 13, 0, 0)
    articles = [
        _article(tmp_path, "concurrent-high"),
        _article(tmp_path, "concurrent-low"),
    ]
    db_session.add_all(articles)
    _account(db_session, "douyin")
    db_session.flush()
    _candidate(db_session, articles[0], "douyin", 90)
    _candidate(db_session, articles[1], "douyin", 80)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )
    factory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    barrier = threading.Barrier(2)
    result_lock = threading.Lock()
    results: list[dict] = []
    errors: list[BaseException] = []

    def run_dispatch() -> None:
        session = factory()
        try:
            barrier.wait(timeout=5)
            result = dispatch_daily_candidates(session, now=now, config=cfg)
            session.commit()
            with result_lock:
                results.append(result)
        except BaseException as exc:
            session.rollback()
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=run_dispatch, name=f"dispatch-{index}")
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    assert sum(len(result["dispatched"]) for result in results) == 1
    db_session.expire_all()
    assert db_session.query(PublishJob).count() == 1
    assert (
        db_session.query(AutoPublishCandidate)
        .filter_by(status="dispatched")
        .count()
        == 1
    )
    assert db_session.query(AutoPublishDispatchLease).count() == 0


def test_dispatch_stops_new_jobs_when_pending_queue_exceeds_two_days(
    db_session, tmp_path, monkeypatch
):
    cfg = _policy(daily_limit=2)
    cfg["publish_policy"]["rollout"] = {"max_queue_days": 2}
    now = datetime(2026, 9, 13, 8, 0)
    article = _article(tmp_path, "backpressure")
    db_session.add(article)
    account = _account(db_session, "douyin")
    db_session.add(
        PublishJob(
            account_id=account.id,
            video_path=article.generated_video_path,
            title="old-pending",
            status="pending",
            created_at=now - timedelta(days=3),
            scheduled_at=now - timedelta(days=2, hours=1),
        )
    )
    _candidate(db_session, article, "douyin", 90)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["douyin"],
    )

    result = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()

    assert result["reason"] == "queue_backpressure"
    assert result["dispatched"] == []
    assert db_session.query(PublishJob).count() == 1


def test_dispatch_skips_killed_platform_but_still_dispatches_shadow(
    db_session, tmp_path, monkeypatch
):
    cfg = _policy(platforms=("wechat_channels", "douyin"), daily_limit=2, shadow=True)
    cfg["publish_policy"]["shadow_mode"] = False
    cfg["publish_policy"]["platforms"]["wechat_channels"].update(
        {
            "enabled": True,
            "shadow_mode": False,
            "kill_switch": {"active": True, "reason": "weak_d1"},
        }
    )
    cfg["publish_policy"]["platforms"]["douyin"].update(
        {"enabled": False, "shadow_mode": True}
    )
    now = datetime(2026, 9, 13, 1, 0)
    wc_article = _article(tmp_path, "killed-wc")
    dy_article = _article(tmp_path, "shadow-dy")
    db_session.add_all([wc_article, dy_article])
    _account(db_session, "wechat_channels")
    _account(db_session, "douyin")
    _candidate(db_session, wc_article, "wechat_channels", 95)
    _candidate(db_session, dy_article, "douyin", 90)
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["wechat_channels", "douyin"],
    )

    result = dispatch_daily_candidates(db_session, now=now, config=cfg)
    db_session.commit()

    platforms = {item["platform"] for item in result["dispatched"]}
    assert platforms == {"douyin"}
    assert (
        db_session.query(AutoPublishCandidate)
        .filter_by(platform="wechat_channels", status="pending")
        .count()
        == 1
    )
