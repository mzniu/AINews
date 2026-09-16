"""API tests for metrics summary endpoint."""
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
    db_path = tmp_path / "test_summary.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def _seed(client):
    from src.db.engine import get_session_factory

    now = datetime.utcnow()
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
                id="job1",
                account_id="acc1",
                video_path="data/videos/a.mp4",
                title="测试作品",
                status="published",
                published_at=now - timedelta(days=5),
            )
        )
        session.flush()
        upsert_metric_snapshot(
            session,
            job_id="job1",
            account_id="acc1",
            platform="xiaohongshu",
            snapshot_date=(now - timedelta(days=4)).date(),
            metrics=PostMetricsItem(platform_post_id="n1", view_count=200, like_count=10),
        )
        session.commit()


def test_metrics_summary_endpoint(client):
    _seed(client)
    resp = client.get("/api/publishing/metrics/summary?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["posts_total"] == 1
    assert data["totals"]["view_count"] == 200
    assert data["totals"]["like_count"] == 10
