from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.utils import paths


def test_get_data_dir_defaults_to_repo_data(monkeypatch, tmp_path):
    monkeypatch.delenv("AINEWS_DATA_DIR", raising=False)
    repo = tmp_path / "repo"
    (repo / "src" / "utils").mkdir(parents=True)
    monkeypatch.setattr(paths, "_detect_resource_dir", lambda: repo)
    paths.get_resource_dir.cache_clear()
    paths.get_data_dir.cache_clear()
    assert paths.get_data_dir() == repo / "data"


def test_get_data_dir_respects_env(monkeypatch, tmp_path):
    custom = tmp_path / "appdata"
    custom.mkdir()
    monkeypatch.setenv("AINEWS_DATA_DIR", str(custom))
    paths.get_data_dir.cache_clear()
    assert paths.get_data_dir() == custom


def test_get_config_dir_under_data_dir(monkeypatch, tmp_path):
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data))
    paths.get_data_dir.cache_clear()
    assert paths.get_config_dir() == data / "config"


def test_runtime_config_path_uses_repo_data_in_development(monkeypatch, tmp_path):
    monkeypatch.delenv("AINEWS_RESOURCE_DIR", raising=False)
    monkeypatch.delenv("AINEWS_DATA_DIR", raising=False)
    repo = tmp_path / "repo"
    monkeypatch.setattr(paths, "_detect_resource_dir", lambda: repo)
    paths.get_resource_dir.cache_clear()
    paths.get_data_dir.cache_clear()

    assert paths.get_runtime_config_path("article_scoring.local.yaml") == (
        repo / "data" / "config" / "article_scoring.local.yaml"
    )


def test_packaged_runtime_config_and_health_use_appdata(monkeypatch, tmp_path):
    resources = tmp_path / "installed-resources"
    data = tmp_path / "AppData" / "AINews" / "data"
    monkeypatch.setenv("AINEWS_RESOURCE_DIR", str(resources))
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data))
    paths.get_resource_dir.cache_clear()
    paths.get_data_dir.cache_clear()
    health_path = Path(__file__).resolve().parents[1] / "api" / "routes" / "health_routes.py"
    spec = importlib.util.spec_from_file_location("task2_health_routes", health_path)
    assert spec is not None and spec.loader is not None
    health_routes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(health_routes)

    config_path = paths.get_runtime_config_path("article_scoring.local.yaml")

    assert paths.get_resource_dir() == resources.resolve()
    assert paths.get_data_dir() == data.resolve()
    assert config_path == data.resolve() / "config" / "article_scoring.local.yaml"
    assert config_path.is_relative_to(paths.get_data_dir())
    assert health_routes.health()["data_dir"] == str(paths.get_data_dir())


def test_resolve_data_path_strips_data_prefix(monkeypatch, tmp_path):
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data))
    paths.get_data_dir.cache_clear()
    assert paths.resolve_data_path("data/videos/foo.mp4") == data / "videos" / "foo.mp4"


def test_to_data_url_path_from_absolute_data_file(monkeypatch, tmp_path):
    data = tmp_path / "appdata"
    ingested = data / "ingested" / "src1" / "art1" / "images"
    ingested.mkdir(parents=True)
    img = ingested / "img_001.jpg"
    img.write_bytes(b"jpg")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data))
    paths.get_data_dir.cache_clear()
    url = paths.to_data_url_path(str(img))
    assert url == "/data/ingested/src1/art1/images/img_001.jpg"
    assert paths.resolve_local_asset_path(url) == img.resolve()


def test_normalize_stored_path_keeps_data_prefix(monkeypatch, tmp_path):
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data))
    paths.get_data_dir.cache_clear()
    assert paths.normalize_stored_path("/data/ingested/a/b.jpg") == "data/ingested/a/b.jpg"


def test_is_packaged_with_resource_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AINEWS_RESOURCE_DIR", str(tmp_path))
    paths.get_resource_dir.cache_clear()
    assert paths.is_packaged() is True
