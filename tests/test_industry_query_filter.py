"""Industry query filter helper (M0a)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.industry.query_filter import apply_active_industry_filter
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource


def _reset_db_engine() -> None:
    import src.db.engine as engine_mod

    engine_mod._engine = None
    engine_mod._SessionLocal = None


def test_apply_active_industry_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "filter.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    _reset_db_engine()
    init_db()
    session: Session = get_session_factory()()
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
                id="a1",
                source_id="src",
                canonical_url="https://example.com/a1",
                title="AI",
                industry_id="tech/ai",
            ),
            IngestedArticle(
                id="a2",
                source_id="src",
                canonical_url="https://example.com/a2",
                title="Macro",
                industry_id="finance/macro",
            ),
        ]
    )
    session.commit()
    query = session.query(IngestedArticle)
    filtered = apply_active_industry_filter(query, IngestedArticle, "tech/ai")
    ids = {row.id for row in filtered.all()}
    assert ids == {"a1"}
    session.close()
