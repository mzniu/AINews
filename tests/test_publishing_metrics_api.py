"""API tests for publish metrics endpoints."""
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.publishing.metrics.snapshot_store import upsert_metric_snapshot
from services.publishing.metrics.adapters.base import PostMetricsItem
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
    db_path = tmp_path / "test_metrics.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def _seed_published(client):
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
                status="active",
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
                platform_post_id="note123",
                platform_post_url="https://www.xiaohongshu.com/explore/note123",
                metrics_match_status="matched",
                published_at=datetime(2026, 8, 10, 12, 0, 0),
            )
        )
        session.flush()
        upsert_metric_snapshot(
            session,
            job_id="job1",
            account_id="acc1",
            platform="xiaohongshu",
            snapshot_date=datetime(2026, 8, 11).date(),
            metrics=PostMetricsItem(
                platform_post_id="note123",
                view_count=100,
                like_count=5,
                follow_count=2,
                play_3s_rate=41.0,
                completion_rate=22.5,
                avg_watch_sec=8.5,
                profile_click_count=3,
            ),
        )
        session.commit()


def test_list_published_posts(client):
    _seed_published(client)
    resp = client.get("/api/publishing/published-posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    post = data["posts"][0]
    assert post["job_id"] == "job1"
    assert post["metrics"]["view_count"] == 100
    assert post["metrics"]["follow_count"] == 2
    assert post["metrics"]["play_3s_rate"] == 41.0
    assert post["metrics"]["completion_rate"] == 22.5
    assert post["metrics"]["avg_watch_sec"] == 8.5
    assert post["metrics"]["profile_click_count"] == 3


def test_list_published_posts_paginates(client):
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
                status="active",
            )
        )
        session.flush()
        for index in range(3):
            session.add(
                PublishJob(
                    id=f"job{index}",
                    account_id="acc1",
                    video_path=f"data/videos/{index}.mp4",
                    title=f"作品{index}",
                    status="published",
                    platform_post_id=f"note{index}",
                    published_at=datetime(2026, 8, 10, 12, index, 0),
                )
            )
        session.commit()

    first = client.get("/api/publishing/published-posts?limit=2&offset=0")
    second = client.get("/api/publishing/published-posts?limit=2&offset=2")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total"] == 3
    assert len(first.json()["posts"]) == 2
    assert len(second.json()["posts"]) == 1
    first_ids = {row["job_id"] for row in first.json()["posts"]}
    second_ids = {row["job_id"] for row in second.json()["posts"]}
    assert first_ids.isdisjoint(second_ids)


def test_get_published_post_metrics_history(client):
    _seed_published(client)
    resp = client.get("/api/publishing/published-posts/job1/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["history"]) == 1
    assert data["history"][0]["view_count"] == 100
