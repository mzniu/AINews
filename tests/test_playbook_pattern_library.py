"""Pattern library API and battle rollups."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.copy_agent.battle_report import build_battle_report
from services.copy_agent.pattern_library import list_pattern_library
from src.db.engine import get_session_factory, init_db
from src.db.models.playbook import CopyAgentJob, PatternCard, PlaybookVersion
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models.publishing_metrics import PublishPostMetricSnapshot
from datetime import datetime, timedelta


@pytest.fixture
def client(db_session):
    from api.routes.copy_agent_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "patterns.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    init_db()
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _v2_card_json(name: str) -> str:
    return json.dumps(
        {
            "pattern": {"name": name, "genre": "short_news_commentary", "purpose": "测"},
            "moves": [{"id": "hook", "function": "钩"}, {"id": "x", "function": "收"}],
            "hook": {"archetype": "curiosity_gap"},
            "motives": {"primary": "emotional_arousal"},
            "verdict": {"kind": "opinion", "function": "controversy_commentary"},
            "evidence_excerpt": "锚",
        },
        ensure_ascii=False,
    )


def test_pattern_library_clusters_same_name(client, db_session):
    for idx, vid in enumerate(("v1", "v2")):
        db_session.add(PlaybookVersion(id=vid, body="b", status="candidate", trap_passed=True))
        db_session.add(
            CopyAgentJob(
                id=f"job{idx}",
                kind="curate",
                status="candidate",
                result_json=json.dumps({"playbook_version_id": vid}, ensure_ascii=False),
            )
        )
        db_session.add(
            PatternCard(
                source_job_id=f"job{idx}",
                card_json=_v2_card_json("对照节奏短评"),
                verdict_kind="opinion",
                verdict_function="controversy_commentary",
            )
        )
    db_session.commit()
    body = client.get("/api/copy-agent/patterns").json()
    assert body["total"] == 1
    assert body["patterns"][0]["count"] == 2
    assert set(body["patterns"][0]["version_ids"]) == {"v1", "v2"}


def test_battle_report_pattern_rollups(db_session):
    published = datetime(2026, 9, 1, 8, 0, 0)
    db_session.add(
        PublisherAccount(
            id="acc",
            platform="douyin",
            session_path="data/publish/sessions/acc.json",
            status="active",
        )
    )
    db_session.commit()
    db_session.add(PlaybookVersion(id="ver1", body="b", status="published", trap_passed=True))
    db_session.add(
        CopyAgentJob(
            id="job1",
            kind="curate",
            status="candidate",
            result_json=json.dumps({"playbook_version_id": "ver1"}, ensure_ascii=False),
        )
    )
    db_session.add(
        PatternCard(
            source_job_id="job1",
            card_json=_v2_card_json("对照节奏短评"),
            verdict_kind="opinion",
            verdict_function="controversy_commentary",
        )
    )
    db_session.add(
        PublishJob(
            id="p1",
            account_id="acc",
            video_path="data/videos/a.mp4",
            title="t",
            playbook_attribution="playbook",
            playbook_version_id="ver1",
            copy_draft_id=None,
            published_at=published,
            status="published",
        )
    )
    db_session.add(
        PublishPostMetricSnapshot(
            job_id="p1",
            account_id="acc",
            platform="douyin",
            snapshot_date=published.date(),
            share_count=7,
            like_count=1,
            fetched_at=published + timedelta(hours=1),
        )
    )
    db_session.commit()
    report = build_battle_report(db_session)
    assert report["pattern_rollups"]
    rollup = report["pattern_rollups"][0]
    assert rollup["pattern_name"] == "对照节奏短评"
    assert rollup["share_count"] == 7
    assert rollup["job_count"] == 1
