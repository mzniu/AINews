"""M0b offline taxonomy stub (bundled packs/taxonomy.yaml)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from web_server import app


def test_me_industry_returns_active_profile(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    import src.db.engine as engine_mod
    from src.db.engine import init_db

    engine_mod._engine = None
    engine_mod._SessionLocal = None
    init_db()

    client = TestClient(app)
    client.put("/api/me/industry", json={"active_industry_id": "tech/ai"})
    response = client.get("/api/me/industry")
    assert response.status_code == 200
    body = response.json()
    assert body["active_industry_id"] == "tech/ai"
    assert body["pack_version"] == "1.0.0"


def test_industry_taxonomy_lists_six_l2_paths():
    client = TestClient(app)
    response = client.get("/api/industry/taxonomy")
    assert response.status_code == 200
    body = response.json()
    paths = []
    for group in body.get("l1") or []:
        for item in group.get("l2") or []:
            paths.append(item["path"])
    assert len(paths) == 6
    assert "tech/ai" in paths
    assert "finance/macro" in paths
