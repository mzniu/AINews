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


def test_get_render_template_includes_yaml(client):
    resp = client.get("/api/ingestion/render-templates/flash_news_portrait")
    assert resp.status_code == 200
    body = resp.json()
    loaded = yaml.safe_load(body["yaml"])
    assert loaded["id"] == "flash_news_portrait"
    assert loaded["layout_kind"] == "classic_overlay"
    assert body["template"]["id"] == "flash_news_portrait"


def test_put_render_template_yaml_updates_typography(client, tmp_path):
    get_resp = client.get("/api/ingestion/render-templates/flash_news_portrait")
    spec = yaml.safe_load(get_resp.json()["yaml"])
    spec.setdefault("typography", {})
    spec["typography"]["title_font_size"] = 91
    resp = client.put(
        "/api/ingestion/render-templates/flash_news_portrait/yaml",
        json={"yaml": yaml.dump(spec, allow_unicode=True)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["template"]["typography"]["title_font_size"] == 91
    local = yaml.safe_load((tmp_path / "config" / "render_templates.local.yaml").read_text(encoding="utf-8"))
    local_row = next(item for item in local["templates"] if item["id"] == "flash_news_portrait")
    assert local_row["typography"]["title_font_size"] == 91


def test_put_render_template_yaml_invalid_400(client):
    resp = client.put(
        "/api/ingestion/render-templates/flash_news_portrait/yaml",
        json={"yaml": "id: [\n"},
    )
    assert resp.status_code == 400


def test_put_render_template_yaml_id_mismatch_400(client):
    resp = client.put(
        "/api/ingestion/render-templates/flash_news_portrait/yaml",
        json={"yaml": "id: other_template\nlayout_kind: classic_overlay\n"},
    )
    assert resp.status_code == 400


def test_put_render_template_yaml_unknown_layout_kind_400(client):
    resp = client.put(
        "/api/ingestion/render-templates/flash_news_portrait/yaml",
        json={"yaml": "id: flash_news_portrait\nlayout_kind: not_a_real_kind\n"},
    )
    assert resp.status_code == 400


def test_put_render_template_json_patch_still_works(client):
    resp = client.put(
        "/api/ingestion/render-templates/flash_news_portrait",
        json={"label": "快讯竖屏（JSON）"},
    )
    assert resp.status_code == 200
    assert resp.json()["template"]["label"] == "快讯竖屏（JSON）"


def test_preview_cover_invalid_yaml_400(client):
    resp = client.post(
        "/api/ingestion/render-templates/preview-cover",
        json={"yaml": "id: [\n"},
    )
    assert resp.status_code == 400


def test_preview_cover_returns_image_url(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()

    def fake_cover(yaml_text: str):
        assert "classic_overlay" in yaml_text
        return {"success": True, "image_url": "/data/cache/template-preview/cover.jpg"}

    monkeypatch.setattr(
        "services.ingestion.template_preview.preview_cover_from_yaml",
        fake_cover,
    )
    resp = client.post(
        "/api/ingestion/render-templates/preview-cover",
        json={"yaml": "layout_kind: classic_overlay\n"},
    )
    assert resp.status_code == 200
    assert resp.json()["image_url"].endswith(".jpg")


def test_preview_video_returns_video_url(client, monkeypatch):
    def fake_video(yaml_text: str):
        return {"success": True, "video_url": "/data/cache/template-preview/clip.mp4"}

    monkeypatch.setattr(
        "services.ingestion.template_preview.preview_video_from_yaml",
        fake_video,
    )
    resp = client.post(
        "/api/ingestion/render-templates/preview-video",
        json={"yaml": "layout_kind: chronicle_frame\n"},
    )
    assert resp.status_code == 200
    assert resp.json()["video_url"].endswith(".mp4")
