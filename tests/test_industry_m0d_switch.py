"""M0d: second L2 pack and switch smoke (finance/macro vs tech/ai)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.industry.config_loader import build_effective_config, refresh_effective_cache
from services.industry.constants import DEFAULT_INDUSTRY_ID
from web_server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    monkeypatch.delenv("AINES_DEV_MODE", raising=False)
    monkeypatch.delenv("AINEWS_ACTIVE_INDUSTRY_ID", raising=False)
    return TestClient(app)


def _enabled_source_ids(effective: dict) -> set[str]:
    sources = (effective.get("ingestion") or {}).get("sources") or []
    return {row["id"] for row in sources if row.get("enabled")}


def _enabled_board_ids(effective: dict) -> set[str]:
    boards = (effective.get("hot_radar") or {}).get("boards") or []
    return {row["id"] for row in boards if row.get("enabled")}


def test_finance_macro_pack_differs_from_tech_ai(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()

    tech = build_effective_config(DEFAULT_INDUSTRY_ID)
    macro = build_effective_config("finance/macro")

    assert macro["industry_id"] == "finance/macro"
    assert "qq_news_fx" in _enabled_source_ids(macro)
    assert "kr36_ai" in _enabled_source_ids(tech)
    assert "kr36_ai" not in _enabled_source_ids(macro)

    tech_boards = _enabled_board_ids(tech)
    macro_boards = _enabled_board_ids(macro)
    assert macro_boards != tech_boards
    assert macro_boards  # at least one finance hot-radar board

    macro_keywords = (macro.get("scoring") or {}).get("ai_relevance_keywords") or []
    assert any(k in macro_keywords for k in ("央行", "GDP", "通胀"))


def test_switch_industry_refreshes_effective_cache(client):
    client.put("/api/me/industry", json={"active_industry_id": "tech/ai"})
    tech = client.get("/api/me/industry").json()
    assert tech["active_industry_id"] == "tech/ai"

    switched = client.post(
        "/api/me/industry/switch",
        json={"active_industry_id": "finance/macro"},
    )
    assert switched.status_code == 200
    body = switched.json()
    assert body["active_industry_id"] == "finance/macro"
    assert body["display_name"] == "宏观财经"
    assert body.get("restart_required") is True

    refresh_effective_cache("finance/macro")
    macro_effective = build_effective_config("finance/macro")
    assert "qq_news_fx" in _enabled_source_ids(macro_effective)


def test_list_articles_scoped_to_active_industry_after_switch(tmp_path, monkeypatch):
    import src.db.engine as engine_mod
    from src.db.engine import get_session_factory, init_db
    from src.db.models.ingestion import IngestedArticle, IngestionSource

    db_path = tmp_path / "ing.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    monkeypatch.delenv("AINES_DEV_MODE", raising=False)
    monkeypatch.delenv("AINEWS_ACTIVE_INDUSTRY_ID", raising=False)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    engine_mod._engine = None
    engine_mod._SessionLocal = None
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
                id="a-tech",
                source_id="src",
                canonical_url="https://example.com/a",
                title="AI title",
                industry_id="tech/ai",
            ),
            IngestedArticle(
                id="a-macro",
                source_id="src",
                canonical_url="https://example.com/b",
                title="Macro title",
                industry_id="finance/macro",
            ),
        ]
    )
    session.commit()
    session.close()

    client = TestClient(app)
    client.put("/api/me/industry", json={"active_industry_id": "finance/macro"})
    resp = client.get("/api/ingestion/articles")
    assert resp.status_code == 200
    payload = resp.json()
    ids = {row["id"] for row in payload.get("articles") or []}
    assert ids == {"a-macro"}
