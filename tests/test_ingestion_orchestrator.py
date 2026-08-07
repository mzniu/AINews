"""Ingestion orchestrator integration tests with in-memory DB."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.engine import Base
from src.db.models.ingestion import IngestedArticle, IngestionJob, IngestionSource
from services.ingestion.orchestrator import IngestionOrchestrator

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "aitnt"


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    ingest_dir = tmp_path / "ingested"
    ingest_dir.mkdir()
    monkeypatch.setattr(
        "services.ingestion.orchestrator.INGESTED_ROOT",
        ingest_dir,
    )
    source = IngestionSource(
        id="aitnt_travel",
        slug="aitnt_travel",
        display_name="AITNT Travel",
        adapter_class="aitnt_news",
        enabled=True,
        schedule_cron="0 * * * *",
        config_json=json.dumps(
            {
                "base_url": "http://travel.aitntnews.com",
                "list_url": "http://travel.aitntnews.com/?index=1",
                "list_pagination": {"type": "query_index", "param": "index", "start": 1},
                "max_list_pages": 1,
                "max_new_articles_per_run": 5,
                "stop_after_existing": 3,
            }
        ),
    )
    session.add(source)
    session.commit()
    yield session, ingest_dir
    session.close()


def test_ingest_from_fixtures_dedupes(db_session, monkeypatch):
    session, ingest_dir = db_session
    list_html = (FIXTURE_DIR / "list_index1.html").read_text(encoding="utf-8")
    detail_html = (FIXTURE_DIR / "detail_27818.html").read_text(encoding="utf-8")

    def fake_fetch(url: str) -> str:
        if "index=" in url or url.endswith("?index=1") or "travel.aitntnews.com/?" in url:
            return list_html
        return detail_html

    monkeypatch.setattr(
        "services.ingestion.adapters.aitnt_news.AitntNewsAdapter.fetch_html",
        lambda self, url: fake_fetch(url),
    )
    monkeypatch.setattr(
        "services.ingestion.asset_downloader.download_image",
        lambda *args, **kwargs: {"success": True, "local_path": "images/img_001.jpg"},
    )

    orch = IngestionOrchestrator(session)
    stats1 = orch.run_source("aitnt_travel")
    assert stats1["new"] >= 1
    article = session.query(IngestedArticle).first()
    assert article is not None
    assert article.view_count == 8706
    assert article.score_grade is not None
    assert article.score_total is not None
    count_after_first = session.query(IngestedArticle).count()

    stats2 = orch.run_source("aitnt_travel")
    assert stats2["new"] == 0
    assert stats2["skipped"] >= 1
    assert session.query(IngestedArticle).count() == count_after_first
