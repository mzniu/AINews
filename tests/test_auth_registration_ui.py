"""Tests for login page registration UI and client-side validation helpers."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUTH_HTML = ROOT / "static" / "auth.html"
AUTH_JS = ROOT / "static" / "js" / "auth.js"
REMOTION_AUTH_HTML = ROOT / "remotion" / "public" / "static" / "auth.html"
REMOTION_AUTH_JS = ROOT / "remotion" / "public" / "static" / "js" / "auth.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "html_path",
    [AUTH_HTML, REMOTION_AUTH_HTML],
    ids=["static", "remotion"],
)
def test_auth_html_exposes_registration_controls(html_path: Path):
    html = _read(html_path)
    assert 'id="phone-mode-toggle"' in html
    assert 'id="email-mode-toggle"' in html
    assert 'id="btn-phone-submit"' in html
    assert 'id="btn-email-submit"' in html
    assert 'id="password-confirm"' in html
    assert "注册" in html


@pytest.mark.parametrize(
    "js_path",
    [AUTH_JS, REMOTION_AUTH_JS],
    ids=["static", "remotion"],
)
def test_auth_js_wires_registration_commands(js_path: Path):
    js = _read(js_path)
    assert "'auth_register'" in js
    assert "'auth_phone_register'" in js
    assert "purpose: phoneMode === 'register' ? 'register' : 'login'" in js
    assert "validatePassword" in js
    assert "两次输入的密码不一致" in js


def test_auth_js_password_minimum_length():
    js = _read(AUTH_JS)
    match = re.search(r"MIN_PASSWORD_LENGTH\s*=\s*(\d+)", js)
    assert match is not None
    assert int(match.group(1)) >= 8


def test_static_and_remotion_auth_assets_stay_in_sync():
    assert _read(AUTH_HTML) == _read(REMOTION_AUTH_HTML)
    assert _read(AUTH_JS) == _read(REMOTION_AUTH_JS)


def test_auth_js_enter_app_defers_navigation_to_tauri():
    js = _read(AUTH_JS)
    assert "appEnterInProgress" in js
    assert "window.location.href" not in js
    assert "await invoke('auth_start_app')" in js
    assert "if (appEnterInProgress) return" in js


@pytest.mark.parametrize(
    "html_path",
    [AUTH_HTML, REMOTION_AUTH_HTML],
    ids=["static", "remotion"],
)
def test_auth_html_startup_loading_overlay(html_path: Path):
    html = _read(html_path)
    assert 'id="startup-loading"' in html
    assert 'class="ripple-ring"' in html
    assert 'id="startup-status"' in html
    assert 'aria-live="polite"' in html
    assert "ainews-mark.png" in html


def test_auth_js_startup_loading_helpers():
    js = _read(AUTH_JS)
    assert "showStartupLoading" in js
    assert "hideStartupLoading" in js
    assert "STARTUP_STATUS_MESSAGES" in js
    assert "showStartupLoading('正在启动应用…')" in js
    assert "showStartupFailure" in js
    assert "auth_get_startup_diagnostics" in js
    assert "ainews:startup-failed" in js


def test_auth_html_startup_error_panel():
    html = _read(AUTH_HTML)
    assert 'id="startup-error"' in html
    assert 'id="startup-error-detail"' in html
    assert 'id="btn-startup-retry"' in html


def test_auth_js_does_not_assign_through_optional_chaining():
    """`obj?.prop = value` is a SyntaxError (Invalid left-hand side in assignment)."""
    js = _read(AUTH_JS)
    assert re.search(r"\?\.[\w$]+\s*=", js) is None


def test_auth_html_theme_script_uses_tauri_asset_path():
    """Tauri frontendDist is `static/`, so `/static/js/...` 404s as HTML (`Unexpected token '<'`)."""
    html = _read(AUTH_HTML)
    assert re.search(r'src="(?:\.?/)?js/shared/theme\.js', html)
    assert "/static/js/shared/theme.js" not in html
