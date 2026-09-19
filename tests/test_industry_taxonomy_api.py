"""M0b offline taxonomy stub (bundled packs/taxonomy.yaml)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from web_server import app


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
