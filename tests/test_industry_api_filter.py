"""API list endpoints filter by active industry (M0a)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.db.engine as engine_mod
from src.db.engine import get_session_factory, init_db


def _reset_db_engine() -> None:
    engine_mod._engine = None
    engine_mod._SessionLocal = None
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.db.models.publishing import AutoPublishCandidate


def _load_ingestion_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "ingestion_routes.py"
    spec = importlib.util.spec_from_file_location("ingestion_routes_industry", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def ingestion_client(tmp_path, monkeypatch):
    db_path = tmp_path / "api_industry.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    monkeypatch.delenv("AINEWS_ACTIVE_INDUSTRY_ID", raising=False)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    _reset_db_engine()
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="src",
            slug="src",
            display_name="Test",
            adapter_class="noop",
        )
    )
    session.flush()
    session.add_all(
        [
            IngestedArticle(
                id="ai-1",
                source_id="src",
                canonical_url="https://example.com/ai",
                title="AI news",
                industry_id="tech/ai",
            ),
            IngestedArticle(
                id="fin-1",
                source_id="src",
                canonical_url="https://example.com/fin",
                title="Macro news",
                industry_id="finance/macro",
            ),
        ]
    )
    session.commit()
    session.close()
    app = FastAPI()
    app.include_router(_load_ingestion_router())
    return TestClient(app)


def test_list_articles_filters_by_default_active_industry(ingestion_client):
    resp = ingestion_client.get("/api/ingestion/articles")
    assert resp.status_code == 200
    payload = resp.json()
    ids = {a["id"] for a in payload["articles"]}
    assert ids == {"ai-1"}
    assert payload["total"] == 1


def test_list_articles_optional_industry_id_override(ingestion_client):
    resp = ingestion_client.get(
        "/api/ingestion/articles", params={"industry_id": "finance/macro"}
    )
    assert resp.status_code == 200
    payload = resp.json()
    ids = {a["id"] for a in payload["articles"]}
    assert ids == {"fin-1"}


def _load_publishing_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes_industry", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def publishing_client(tmp_path, monkeypatch):
    db_path = tmp_path / "pub_industry.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    _reset_db_engine()
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="src",
            slug="src",
            display_name="Test",
            adapter_class="noop",
        )
    )
    session.flush()
    session.add_all(
        [
            IngestedArticle(
                id="art-ai",
                source_id="src",
                canonical_url="https://example.com/a",
                title="A",
                industry_id="tech/ai",
            ),
            IngestedArticle(
                id="art-fin",
                source_id="src",
                canonical_url="https://example.com/b",
                title="B",
                industry_id="finance/macro",
            ),
        ]
    )
    session.add_all(
        [
            AutoPublishCandidate(
                id="c-ai",
                article_id="art-ai",
                platform="douyin",
                action="publish",
                recommended_action="publish",
                policy_version="v1",
                industry_id="tech/ai",
            ),
            AutoPublishCandidate(
                id="c-fin",
                article_id="art-fin",
                platform="douyin",
                action="publish",
                recommended_action="publish",
                policy_version="v1",
                industry_id="finance/macro",
            ),
        ]
    )
    session.commit()
    session.close()
    app = FastAPI()
    app.include_router(_load_publishing_router())
    return TestClient(app)


def test_list_candidates_filters_by_active_industry(publishing_client):
    resp = publishing_client.get("/api/publishing/candidates")
    assert resp.status_code == 200
    payload = resp.json()
    ids = {item["id"] for item in payload["items"]}
    assert ids == {"c-ai"}
    assert payload["total"] == 1
