"""Desktop installer: portable bundled Python venv."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELOCATE = ROOT / "desktop" / "scripts" / "relocate-bundled-python.ps1"
BUILD_RELEASE = ROOT / "desktop" / "scripts" / "build-release.ps1"
BUILD_FAST = ROOT / "desktop" / "scripts" / "build-release-fast.ps1"


def test_relocate_bundled_python_script_exists():
    assert RELOCATE.is_file()
    text = RELOCATE.read_text(encoding="utf-8")
    assert "python*.zip" in text or "python311.zip" in text
    assert "pyvenv.cfg" in text


def test_backend_has_runtime_python_repair():
    backend_rs = (ROOT / "desktop" / "src-tauri" / "src" / "backend.rs").read_text(
        encoding="utf-8"
    )
    assert "ensure_bundled_python_config" in backend_rs
    assert "prepare_python_runtime" in backend_rs
    assert "PYTHONHOME" in backend_rs
    assert "bundled_portable_launch" in backend_rs
    assert "PermissionDenied" in backend_rs


def test_release_build_scripts_invoke_relocate():
    release = BUILD_RELEASE.read_text(encoding="utf-8")
    fast = BUILD_FAST.read_text(encoding="utf-8")
    assert "relocate-bundled-python.ps1" in release
    assert "relocate-bundled-python.ps1" in fast
