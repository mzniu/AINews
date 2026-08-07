"""Database engine and session factory."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.utils.config import Config


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    env_url = os.getenv("INGESTION_DATABASE_URL")
    if env_url:
        return env_url
    db_path = Config.ROOT_DIR / "data" / "ainews.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def create_app_engine(database_url: str | None = None):
    url = database_url or _database_url()
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 60},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_app_engine()
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_factory():
    get_engine()
    return _SessionLocal


def _ensure_sqlite_columns(engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(ingested_articles)")).fetchall()
        columns = {row[1] for row in rows}
        migrations = {
            "view_count": "INTEGER",
            "score_total": "REAL",
            "score_grade": "VARCHAR(8)",
            "score_breakdown_json": "TEXT",
            "score_comment": "TEXT",
            "scored_at": "DATETIME",
            "images_scored_at": "DATETIME",
            "images_score_summary_json": "TEXT",
            "video_draft_json": "TEXT",
            "video_draft_generated_at": "DATETIME",
            "video_prep_at": "DATETIME",
            "video_prep_status_json": "TEXT",
            "generated_video_path": "VARCHAR(512)",
            "generated_video_at": "DATETIME",
            "selected_bgm_path": "VARCHAR(512)",
            "selected_images_json": "TEXT",
            "media_pipeline_status": "VARCHAR(32)",
            "generated_cover_path": "VARCHAR(512)",
        }
        for name, col_type in migrations.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE ingested_articles ADD COLUMN {name} {col_type}"))

        pub_rows = conn.execute(text("PRAGMA table_info(publish_jobs)")).fetchall()
        pub_columns = {row[1] for row in pub_rows}
        if pub_columns and "scheduled_at" not in pub_columns:
            conn.execute(text("ALTER TABLE publish_jobs ADD COLUMN scheduled_at DATETIME"))


def init_db(database_url: str | None = None) -> None:
    global _engine, _SessionLocal
    import src.db.models.ingestion  # noqa: F401 — register ORM tables
    import src.db.models.publishing  # noqa: F401 — register ORM tables

    _engine = create_app_engine(database_url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(_engine)
    _ensure_sqlite_columns(_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
