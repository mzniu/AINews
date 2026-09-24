import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.runtime_routes import router


@pytest.fixture
def client(runtime_dirs, monkeypatch):
    config_dir, _ = runtime_dirs
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.CONFIG_PATH",
        config_dir / "desktop_runtime.local.yaml",
    )
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.is_packaged",
        lambda: True,
    )
    monkeypatch.setattr(
        "api.routes.runtime_routes.remotion_available",
        lambda: False,
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def runtime_dirs(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return config_dir, data_dir


def test_get_put_video_renderer(client):
    get_resp = client.get("/api/runtime/video-renderer")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["preferred"] == "auto"
    assert body["active"] == "python"
    assert body["remotion"]["ready"] is False
    assert "python" in body

    put_resp = client.put(
        "/api/runtime/video-renderer",
        json={"preferred": "python", "allow_python_fallback": False},
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["preferred"] == "python"
    assert updated["allow_python_fallback"] is False
