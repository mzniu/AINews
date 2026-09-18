"""Desktop first-run: slim bundle + runtime setup hooks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_slim_bundle_requirements_exclude_lama():
    slim = (ROOT / "requirements-desktop-bundle.txt").read_text(encoding="utf-8")
    assert "simple-lama-inpainting" not in slim
    extras = (ROOT / "requirements-desktop-extras.txt").read_text(encoding="utf-8")
    assert "simple-lama-inpainting" in extras


def test_rust_runtime_setup_module():
    lib_rs = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "mod runtime_setup" in lib_rs
    backend_rs = (ROOT / "desktop" / "src-tauri" / "src" / "backend.rs").read_text(encoding="utf-8")
    assert "resolve_playwright_browsers_path" in backend_rs


def test_auth_ui_setup_progress():
    auth_html = (ROOT / "static" / "auth.html").read_text(encoding="utf-8")
    auth_js = (ROOT / "static" / "js" / "auth.js").read_text(encoding="utf-8")
    assert "startup-progress" in auth_html
    assert "runtime_setup_run" in auth_js
    assert "ainews:setup-progress" in auth_js
