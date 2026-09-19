"""Tests for hot radar discovery queue API."""
from __future__ import annotations

import json
from datetime import datetime

from services.ingestion.hot_radar_discovery import (
    enqueue_hot_url_discoveries,
    get_hot_radar_discovery_queue_view,
)
from services.ingestion.hot_radar_service import seed_hot_radar_snapshot
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import CrawlRun, IngestedArticle, IngestionJob, IngestionSource


def test_get_hot_radar_discovery_queue_view_lists_jobs(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    cfg_path = tmp_path / "hot_radar.yaml"
    cfg_path.write_text(
        """
enabled: true
boards:
  - id: test_board
    hashid: hashboardaaa01
    name: IT之家
    display: AI
    enabled: true
discovery:
  enabled: true
  max_rank: 10
  max_urls_per_refresh: 5
  per_board_max: 5
  domain_source_map:
    ithome.com: ithome_it
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DISABLE_EFFECTIVE_CONFIG", "1")
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", cfg_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", tmp_path / "hot_radar.local.yaml")
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="ithome_it",
            slug="ithome_it",
            display_name="IT之家",
            adapter_class="ithome_news",
            enabled=True,
        )
    )
    session.commit()

    seed_hot_radar_snapshot(
        session,
        board="hashboardaaa01",
        fetched_at=datetime.utcnow(),
        items=[
            {"rank": 3, "title": "热榜文章A", "url": "https://m.ithome.com/html/9.htm", "heat_label": "10万"},
        ],
    )
    enqueue_hot_url_discoveries(session)

    job = session.query(IngestionJob).filter_by(job_type="hot_radar_discovery").one()
    article = IngestedArticle(
        source_id="ithome_it",
        canonical_url="https://m.ithome.com/html/9.htm",
        title="热榜文章A",
    )
    session.add(article)
    session.flush()
    run = CrawlRun(source_id="ithome_it", job_id=job.id, status="succeeded")
    session.add(run)
    session.flush()
    article.crawl_run_id = run.id
    job.status = "succeeded"
    job.finished_at = datetime.utcnow()
    session.commit()

    view = get_hot_radar_discovery_queue_view(session)
    assert view["summary"]["succeeded"] == 1
    assert len(view["items"]) == 1
    row = view["items"][0]
    assert row["job_id"] == job.id
    assert row["title"] == "热榜文章A"
    assert row["article_id"] == article.id
    assert row["board_label"] == "IT之家·AI"
    assert row["rank"] == 3


def test_discovery_queue_resolves_article_from_result_payload(tmp_path, monkeypatch):
    db_path = tmp_path / "queue2.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="ithome_it",
            slug="ithome_it",
            display_name="IT之家",
            adapter_class="ithome_news",
            enabled=True,
        )
    )
    session.commit()
    article = IngestedArticle(
        source_id="ithome_it",
        canonical_url="https://m.ithome.com/html/9.htm",
        title="已存在文章",
    )
    session.add(article)
    session.flush()
    job = IngestionJob(
        job_type="hot_radar_discovery",
        source_id="ithome_it",
        status="succeeded",
        finished_at=datetime.utcnow(),
        payload_json=json.dumps(
            {
                "url": "https://m.ithome.com/html/9.htm",
                "title": "已存在文章",
                "source_id": "ithome_it",
                "result": {"skipped": 1, "article_id": article.id},
            },
            ensure_ascii=False,
        ),
    )
    session.add(job)
    session.commit()

    view = get_hot_radar_discovery_queue_view(session)
    row = view["items"][0]
    assert row["outcome"] == "skipped"
    assert row["article_id"] == article.id
