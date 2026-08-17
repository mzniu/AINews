"""API tests for render template endpoints."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_templates_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "render_template_routes.py"
    spec = importlib.util.spec_from_file_location("render_template_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    base_path = tmp_path / "config" / "render_templates.yaml"
    local_path = tmp_path / "config" / "render_templates.local.yaml"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(
        yaml.dump(
            {
                "version": 1,
                "default_template_id": "flash_news_portrait",
                "templates": [
                    {
                        "id": "flash_news_portrait",
                        "label": "快讯竖屏（默认）",
                        "builtin": True,
                        "layout_kind": "classic_overlay",
                        "canvas": {"width": 1080, "height": 1440, "fps": 24},
                    },
                    {
                        "id": "chronicle_archive_tech_blue",
                        "label": "小牛聊AI档案（科技蓝）",
                        "builtin": True,
                        "layout_kind": "chronicle_frame",
                        "canvas": {"width": 1080, "height": 1920, "fps": 24},
                        "cover": {"crop": "top", "height": 1440},
                    },
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "services.ingestion.render_templates.RENDER_TEMPLATES_BASE_PATH", base_path
    )
    monkeypatch.setattr(
        "services.ingestion.render_templates.RENDER_TEMPLATES_LOCAL_PATH", local_path
    )
    app = FastAPI()
    app.include_router(_load_templates_router())
    return TestClient(app)


def test_list_render_templates(client):
    resp = client.get("/api/ingestion/render-templates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["default_template_id"] == "flash_news_portrait"
    ids = {item["id"] for item in body["templates"]}
    assert "flash_news_portrait" in ids
    assert "chronicle_archive_tech_blue" in ids


def test_set_default_render_template(client):
    resp = client.put(
        "/api/ingestion/render-templates/default",
        json={"template_id": "chronicle_archive_tech_blue"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_template_id"] == "chronicle_archive_tech_blue"


def test_set_default_unknown_template_400(client):
    resp = client.put(
        "/api/ingestion/render-templates/default",
        json={"template_id": "nope"},
    )
    assert resp.status_code == 400
