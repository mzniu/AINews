from __future__ import annotations

import pytest

from app.config import get_settings
from app.database import get_engine, reset_engine_for_tests
from pathlib import Path

from app.models import Base
from scripts.seed_industry_packs import seed


@pytest.fixture(autouse=True)
def cloud_test_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / "cloud.db"
    packs_root = tmp_path / "packs"
    repo_packs = Path(__file__).resolve().parents[2] / "packs"
    if repo_packs.is_dir():
        import shutil

        shutil.copytree(repo_packs, packs_root)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_AUTH_JWT_SECRET", "test-secret")
    monkeypatch.setenv("AINEWS_AUTH_APP_ID", "app_ai_news")
    monkeypatch.setenv("PACKS_ROOT", str(packs_root))
    get_settings.cache_clear()
    reset_engine_for_tests()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    if packs_root.is_dir() and (packs_root / "taxonomy.yaml").is_file():
        seed()
    yield
    reset_engine_for_tests()
    get_settings.cache_clear()
