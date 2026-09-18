"""SQLite industry_id column migration (M0a)."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from src.db.engine import _ensure_sqlite_columns, init_db


def _legacy_articles_ddl(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE ingested_articles (
                id VARCHAR(32) PRIMARY KEY,
                source_id VARCHAR(64) NOT NULL,
                canonical_url VARCHAR(1024) NOT NULL,
                title VARCHAR(512) DEFAULT '',
                status VARCHAR(32) DEFAULT 'fetched',
                keywords_json TEXT DEFAULT '[]',
                tags_json TEXT DEFAULT '[]',
                created_at DATETIME
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO ingested_articles (id, source_id, canonical_url, title)
            VALUES ('legacy1', 'src', 'https://example.com/1', 'Legacy article')
            """
        )
    )


def test_migration_adds_industry_id_to_legacy_articles(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        _legacy_articles_ddl(conn)
    _ensure_sqlite_columns(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(ingested_articles)")).fetchall()
        columns = {row[1] for row in rows}
        assert "industry_id" in columns
        value = conn.execute(
            text("SELECT industry_id FROM ingested_articles WHERE id = 'legacy1'")
        ).scalar_one()
        assert value == "tech/ai"


def test_fresh_init_db_has_industry_id_on_models(tmp_path, monkeypatch):
    import src.db.engine as engine_mod

    db_path = tmp_path / "fresh.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    engine_mod._engine = None
    engine_mod._SessionLocal = None
    init_db()
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as conn:
        for table in (
            "ingested_articles",
            "auto_publish_candidates",
            "hot_radar_snapshots",
            "hot_radar_article_matches",
        ):
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            if not rows:
                continue
            columns = {row[1] for row in rows}
            assert "industry_id" in columns, table
