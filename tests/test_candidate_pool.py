"""API tests for candidate pool management."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db.engine import init_db


def _load_publishing_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes_candidate_pool", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_candidate_pool.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    init_db()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def test_list_candidates_empty(client):
    response = client.get("/api/publishing/candidates")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total"] == 0
    assert payload["items"] == []


def test_skip_unknown_candidate_returns_404(client):
    response = client.post("/api/publishing/candidates/no-such-id/skip")
    assert response.status_code == 404


def test_enqueue_unknown_candidate_returns_404(client):
    response = client.post("/api/publishing/candidates/no-such-id/enqueue")
    assert response.status_code == 404


def test_skip_and_list_candidate(client):
    from src.db.engine import session_scope
    from src.db.models.ingestion import IngestedArticle, IngestionSource
    from src.db.models.publishing import AutoPublishCandidate

    with session_scope() as session:
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
        session.flush()
        article = IngestedArticle(
            source_id="src1",
            canonical_url="https://example.com/candidate-pool",
            title="candidate-pool-test",
        )
        session.add(article)
        session.flush()
        candidate = AutoPublishCandidate(
            article_id=article.id,
            platform="douyin",
            policy_version="1",
            action="publish",
            recommended_action="publish",
            priority=88.0,
            reasons_json='["test"]',
            status="pending",
        )
        session.add(candidate)
        session.flush()
        candidate_id = candidate.id

    listed = client.get("/api/publishing/candidates?status=pending&platform=douyin")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "candidate-pool-test"

    skipped = client.post(f"/api/publishing/candidates/{candidate_id}/skip")
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped"


def test_purge_removes_stale_candidates_by_article_age(client):
    from datetime import datetime, timedelta

    from src.db.engine import session_scope
    from src.db.models.ingestion import IngestedArticle, IngestionSource
    from src.db.models.publishing import AutoPublishCandidate

    now = datetime.utcnow()
    old = now - timedelta(days=10)
    fresh = now - timedelta(days=2)

    with session_scope() as session:
        session.add(
            IngestionSource(
                id="src-purge",
                slug="src-purge",
                display_name="Purge",
                adapter_class="aitnt_news",
                enabled=True,
                schedule_cron="0 * * * *",
            )
        )
        session.flush()

        def add_article(url: str, *, published_at, created_at) -> IngestedArticle:
            article = IngestedArticle(
                source_id="src-purge",
                canonical_url=url,
                title=url,
                published_at=published_at,
                created_at=created_at,
            )
            session.add(article)
            session.flush()
            return article

        def add_candidate(article: IngestedArticle, status: str, platform: str = "douyin") -> str:
            row = AutoPublishCandidate(
                article_id=article.id,
                platform=platform,
                policy_version="1",
                action="publish",
                recommended_action="publish",
                priority=50.0,
                reasons_json="[]",
                status=status,
                created_at=now,
            )
            session.add(row)
            session.flush()
            return row.id

        stale_published = add_article(
            "https://example.com/stale-published",
            published_at=old,
            created_at=now,
        )
        stale_ingested = add_article(
            "https://example.com/stale-ingested",
            published_at=None,
            created_at=old,
        )
        fresh_published = add_article(
            "https://example.com/fresh-published",
            published_at=fresh,
            created_at=old,
        )
        dispatched_article = add_article(
            "https://example.com/dispatched-old",
            published_at=old,
            created_at=old,
        )
        stale_pending_id = add_candidate(stale_published, "pending")
        stale_deferred_id = add_candidate(stale_ingested, "deferred")
        stale_skipped_id = add_candidate(stale_published, "skipped", platform="kuaishou")
        fresh_id = add_candidate(fresh_published, "pending")
        dispatched_id = add_candidate(dispatched_article, "dispatched")
        article_ids = {
            stale_published.id,
            stale_ingested.id,
            fresh_published.id,
            dispatched_article.id,
        }

    response = client.post(
        "/api/publishing/candidates/purge",
        json={"older_than_days": 7},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["deleted"] == 3
    assert payload["older_than_days"] == 7

    with session_scope() as session:
        remaining = {
            row.id
            for row in session.query(AutoPublishCandidate).all()
        }
        assert stale_pending_id not in remaining
        assert stale_deferred_id not in remaining
        assert stale_skipped_id not in remaining
        assert fresh_id in remaining
        assert dispatched_id in remaining
        kept_articles = {
            row.id for row in session.query(IngestedArticle).all()
        }
        assert article_ids <= kept_articles


def test_purge_rejects_non_positive_days(client):
    response = client.post(
        "/api/publishing/candidates/purge",
        json={"older_than_days": 0},
    )
    assert response.status_code == 422
