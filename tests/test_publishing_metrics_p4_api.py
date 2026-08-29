"""API tests for P4 metrics features."""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.snapshot_store import upsert_metric_snapshot
from src.db.engine import init_db
from src.db.models.publishing import PublishJob, PublisherAccount


def _load_publishing_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_p4.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def _seed_job(job_id: str = "job1", *, status: str = "unmatched"):
    from src.db.engine import get_session_factory

    factory = get_session_factory()
    with factory() as session:
        session.add(
            PublisherAccount(
                id="acc1",
                platform="xiaohongshu",
                nickname="测试号",
                platform_uid="uid1",
                session_path="data/publish/sessions/acc1.enc",
            )
        )
        session.flush()
        session.add(
            PublishJob(
                id=job_id,
                account_id="acc1",
                video_path="data/videos/a.mp4",
                title="P4测试",
                status="published",
                platform_post_id="xhs_1",
                metrics_match_status=status,
                published_at=datetime(2026, 8, 10, 12, 0, 0),
            )
        )
        session.commit()


def test_bind_published_post_api(client):
    _seed_job()
    resp = client.post(
        "/api/publishing/published-posts/job1/bind",
        json={
            "platform_post_id": "manual-note-1",
            "platform_post_url": "https://www.xiaohongshu.com/explore/manual-note-1",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform_post_id"] == "manual-note-1"
    assert data["metrics_match_status"] == "manual_matched"


def test_export_published_posts_csv(client):
    from src.db.engine import get_session_factory

    _seed_job()
    factory = get_session_factory()
    with factory() as session:
        upsert_metric_snapshot(
            session,
            job_id="job1",
            account_id="acc1",
            platform="xiaohongshu",
            snapshot_date=datetime(2026, 8, 11).date(),
            metrics=PostMetricsItem(platform_post_id="manual-note-1", view_count=88),
        )
        session.commit()
    resp = client.get("/api/publishing/published-posts/export?days=30")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "P4测试" in resp.text


def test_metrics_alerts_api(client):
    from src.db.engine import get_session_factory

    _seed_job()
    factory = get_session_factory()
    now = datetime.utcnow()
    with factory() as session:
        upsert_metric_snapshot(
            session,
            job_id="job1",
            account_id="acc1",
            platform="xiaohongshu",
            snapshot_date=(now - timedelta(days=2)).date(),
            metrics=PostMetricsItem(platform_post_id="n1", view_count=1000),
        )
        upsert_metric_snapshot(
            session,
            job_id="job1",
            account_id="acc1",
            platform="xiaohongshu",
            snapshot_date=(now - timedelta(days=1)).date(),
            metrics=PostMetricsItem(platform_post_id="n1", view_count=400),
        )
        session.commit()

    resp = client.get("/api/publishing/metrics/alerts?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["drop_pct"] == 60.0
