import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_health_path = Path(__file__).resolve().parents[1] / "api" / "routes" / "health_routes.py"
_spec = importlib.util.spec_from_file_location("health_routes", _health_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

app = FastAPI()
app.include_router(_mod.router)


def test_health_ok():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "data_dir" in body
