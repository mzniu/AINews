"""TDD for desktop video renderer preferences (spec v1.1 §6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.ingestion.video_renderer_config import (
    choose_renderer_for_render,
    compute_active_renderer,
    default_preferred_renderer,
    load_desktop_runtime_config,
    remotion_marker_path,
    save_desktop_runtime_config,
    check_upgrade_required,
    sha256_file,
)


@pytest.fixture
def runtime_dirs(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("services.ingestion.video_renderer_config.CONFIG_PATH", config_dir / "desktop_runtime.local.yaml")
    monkeypatch.setattr("services.ingestion.video_renderer_config.get_data_dir", lambda: data_dir)
    return config_dir, data_dir


def test_default_preferred_packaged_is_auto(monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.is_packaged",
        lambda: True,
    )
    assert default_preferred_renderer() == "auto"


def test_default_preferred_dev_is_remotion(monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.is_packaged",
        lambda: False,
    )
    assert default_preferred_renderer() == "remotion"


def test_load_save_desktop_runtime_config(runtime_dirs, monkeypatch):
    _, _ = runtime_dirs
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.is_packaged",
        lambda: True,
    )
    cfg = load_desktop_runtime_config()
    assert cfg["video_renderer"]["preferred"] == "auto"
    assert cfg["video_renderer"]["allow_python_fallback"] is True

    saved = save_desktop_runtime_config({"preferred": "python", "allow_python_fallback": False})
    assert saved["video_renderer"]["preferred"] == "python"
    assert saved["video_renderer"]["allow_python_fallback"] is False
    again = load_desktop_runtime_config()
    assert again["video_renderer"]["preferred"] == "python"


@pytest.mark.parametrize(
    "preferred,ready,fallback,expected_active",
    [
        ("python", True, True, "python"),
        ("python", False, True, "python"),
        ("auto", False, True, "python"),
        ("auto", True, True, "remotion"),
        ("remotion", False, True, "python"),
        ("remotion", True, True, "remotion"),
    ],
)
def test_compute_active_renderer(preferred, ready, fallback, expected_active):
    active, _ = compute_active_renderer(
        preferred=preferred,
        allow_python_fallback=fallback,
        remotion_ready=ready,
        env_override=None,
    )
    assert active == expected_active


def test_compute_active_renderer_env_overrides_yaml():
    active, _ = compute_active_renderer(
        preferred="auto",
        allow_python_fallback=True,
        remotion_ready=True,
        env_override="python",
    )
    assert active == "python"


def test_choose_renderer_fail_when_remotion_required_but_not_ready():
    choice = choose_renderer_for_render(
        preferred="remotion",
        allow_python_fallback=False,
        remotion_ready=False,
        env_override=None,
        call_override=None,
    )
    assert choice.action == "fail"
    assert choice.error == "remotion_not_ready"


def test_choose_renderer_env_beats_config():
    choice = choose_renderer_for_render(
        preferred="python",
        allow_python_fallback=True,
        remotion_ready=True,
        env_override="remotion",
        call_override=None,
    )
    assert choice.action == "remotion"


def test_choose_renderer_call_override_beats_env():
    choice = choose_renderer_for_render(
        preferred="auto",
        allow_python_fallback=True,
        remotion_ready=True,
        env_override="remotion",
        call_override="python",
    )
    assert choice.action == "python"


def test_check_upgrade_required_when_lock_changes(tmp_path):
    lock = tmp_path / "package-lock.json"
    lock.write_text('{"lockfileVersion": 1}', encoding="utf-8")
    digest = sha256_file(lock)
    marker = {"app_version": "1.0.0", "remotion_lock_sha256": digest}
    assert check_upgrade_required(marker, "1.0.0", lock) is False
    lock.write_text('{"lockfileVersion": 2}', encoding="utf-8")
    assert check_upgrade_required(marker, "1.0.0", lock) is True
    assert check_upgrade_required(marker, "1.0.15", lock) is True


def test_remotion_marker_path(runtime_dirs):
    _, data_dir = runtime_dirs
    assert remotion_marker_path() == data_dir / "runtime" / "remotion_v1.json"


def test_write_marker_roundtrip(runtime_dirs):
    _, data_dir = runtime_dirs
    path = remotion_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"install_id": "remotion_v1", "app_version": "1.0.15"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    from services.ingestion.video_renderer_config import load_remotion_marker

    assert load_remotion_marker() == payload
