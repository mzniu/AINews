"""M0b: ingestion DB sync respects effective industry pack source enablement."""
from __future__ import annotations

import pytest

from services.industry.config_loader import build_effective_config, write_effective_cache
from services.industry.constants import DEFAULT_INDUSTRY_ID
from services.ingestion.registry import sync_sources_to_db
from src.db.engine import Base
from src.db.models.ingestion import IngestionSource


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    db_path = tmp_path / "ainews.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_sync_sources_disables_sources_outside_effective_pack(
    db_session, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="test",
    )
    sync_sources_to_db(db_session)
    rows = {row.id: row for row in db_session.query(IngestionSource).all()}
    assert rows["kr36_ai"].enabled is True
    assert rows["aitnt_travel"].enabled is False
