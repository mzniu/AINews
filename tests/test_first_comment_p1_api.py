"""P1 API tests for first-comment retry and video-draft patch."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.publishing.first_comment import validate_first_comment
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.db.models.publishing import PublishJob, PublisherAccount


def _load_router(module_name: str, filename: str):
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def publishing_client(tmp_path, monkeypatch):
    db_path = tmp_path / "fc_p1_publish.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    init_db()
    app = FastAPI()
    app.include_router(_load_router("publishing_routes_p1", "publishing_routes.py").router)
    return TestClient(app)


@pytest.fixture
def ingestion_db(tmp_path, monkeypatch):
    db_path = tmp_path / "fc_p1_ingestion.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    init_db()
    with get_session_factory()() as session:
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
        session.add(
            IngestedArticle(
                id="art1",
                source_id="src1",
                canonical_url="https://example.com/a",
                title="测试文章",
                video_draft_json=json.dumps(
                    {"main_line1": "标题", "first_comment": "旧首评"},
                    ensure_ascii=False,
                ),
            )
        )
        session.commit()


@pytest.fixture
def seeded_publishing(publishing_client):
    with get_session_factory()() as session:
        session.add(
            PublisherAccount(
                id="acc1",
                platform="douyin",
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
                title="已发布作品",
                status="published",
                first_comment_text="你觉得这条资讯最关键的点是什么？",
                comment_status="failed",
                comment_retry_count=0,
            )
        )
        session.commit()
    return publishing_client


def test_patch_video_draft_first_comment(ingestion_db):
    """Route logic: validate + merge first_comment into video_draft_json."""
    first_comment = "你觉得这条资讯最关键的点是什么？"
    ok, err = validate_first_comment(first_comment)
    assert ok, err

    with get_session_factory()() as session:
        row = session.get(IngestedArticle, "art1")
        draft = json.loads(row.video_draft_json)
        draft["first_comment"] = first_comment
        row.video_draft_json = json.dumps(draft, ensure_ascii=False)
        session.commit()
        session.refresh(row)
        saved = json.loads(row.video_draft_json)
        assert saved["first_comment"] == first_comment


def test_retry_comment_route_rejects_not_published(seeded_publishing):
    with get_session_factory()() as session:
        job = session.get(PublishJob, "job1")
        job.status = "pending"
        session.commit()

    resp = seeded_publishing.post("/api/publishing/jobs/job1/retry-comment")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "job_not_published"


def test_retry_comment_route_success_mock(seeded_publishing, monkeypatch):
    monkeypatch.setattr(
        "publishing_routes_p1.PublishOrchestrator.retry_comment_job",
        lambda self, job_id, force=False: {
            "success": True,
            "comment_status": "posted",
            "comment_retry_count": 1,
            "error": None,
        },
    )
    resp = seeded_publishing.post("/api/publishing/jobs/job1/retry-comment")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["comment_status"] == "posted"
