"""P1 UI/UX redesign — video pages, settings nav, pipeline, metrics, search, dark mode."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
DESIGN_TOKENS = STATIC / "css" / "design-system" / "tokens.css"
VIDEO_MAKER = STATIC / "video_maker.html"
VIDEO_MAKER_CSS = STATIC / "css" / "video_maker.css"
VIDEO_EDITOR3 = STATIC / "video_editor3.html"
VIDEO_EDITOR3_CSS = STATIC / "css" / "video_editor3.css"
SETTINGS_HTML = STATIC / "settings.html"
SETTINGS_CSS = STATIC / "css" / "model_settings.css"
PIPELINE_JS = STATIC / "js" / "shared" / "pipeline_stepper.js"
PIPELINE_CSS = STATIC / "css" / "components" / "pipeline_bar.css"
PUBLISH_METRICS = STATIC / "publish_metrics.html"
PUBLISH_METRICS_CSS = STATIC / "css" / "publish_metrics.css"
PUBLISH_METRICS_JS = STATIC / "js" / "publish_center_metrics.js"
APP_NAV_JS = STATIC / "js" / "shared" / "app_nav.js"
GLOBAL_SEARCH_JS = STATIC / "js" / "shared" / "global_search.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _search_client() -> TestClient:
    from src.db.engine import init_db

    init_db()
    path = ROOT / "api" / "routes" / "search_routes.py"
    spec = importlib.util.spec_from_file_location("search_routes", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


# --- 1. video_maker / video_editor3 design tokens ---


def test_video_maker_uses_design_tokens_and_external_css():
    html = _read(VIDEO_MAKER)
    assert VIDEO_MAKER_CSS.is_file()
    assert "video_maker.css" in html
    assert "tokens.css" in html
    assert "app_shell.css" in html
    assert re.search(r"<title>AINews · 视频制作</title>", html)
    assert "#667eea" not in html


def test_video_maker_css_uses_soft_card_tokens():
    css = _read(VIDEO_MAKER_CSS)
    assert "var(--app-border)" in css or "var(--color-border)" in css
    assert "soft-card" in css or "var(--color-surface" in css
    assert "#667eea" not in css


def test_video_editor3_uses_app_shell_not_purple_gradient():
    html = _read(VIDEO_EDITOR3)
    css = _read(VIDEO_EDITOR3_CSS)
    assert "tokens.css" in html
    assert "app_shell.css" in html
    assert "667eea" not in css
    assert "764ba2" not in css
    assert re.search(r"<title>AINews · 视频文字编辑器</title>", html)


def test_video_editor3_css_supports_dark_theme():
    css = _read(VIDEO_EDITOR3_CSS)
    assert '[data-theme="dark"]' in css or "var(--app-" in css or "var(--color-" in css


# --- 2. Settings vertical sub-nav ---


def test_settings_page_has_vertical_subnav_layout():
    html = _read(SETTINGS_HTML)
    assert "settings-layout" in html
    assert "settings-subnav" in html
    assert "settings-content" in html


def test_settings_css_vertical_subnav_on_wide_screen():
    css = _read(SETTINGS_CSS)
    assert "settings-layout" in css
    assert "settings-subnav" in css
    assert re.search(r"@media\s*\(\s*min-width:\s*1280px\s*\)", css)
    assert "flex-direction: column" in css or "grid-template" in css


# --- 3. Pipeline stepper cross-page sync ---


def test_pipeline_stepper_module_exists():
    assert PIPELINE_JS.is_file()
    js = _read(PIPELINE_JS)
    assert "PIPELINE_STEPS" in js or "STEPS" in js
    assert "localStorage" in js
    assert "setActiveStep" in js or "syncFromPath" in js


def test_pipeline_bar_css_exists():
    assert PIPELINE_CSS.is_file()
    css = _read(PIPELINE_CSS)
    assert "pipeline-bar" in css


@pytest.mark.parametrize(
    "page",
    [
        "ingestion_library.html",
        "hot_radar.html",
        "video_maker.html",
        "publish_center.html",
    ],
)
def test_pipeline_pages_include_stepper_script(page: str):
    html = _read(STATIC / page)
    assert "pipeline_stepper.js" in html


# --- 4. publish_metrics data-dense layout ---


def test_publish_metrics_has_kpi_sparkline_and_sortable_table():
    html = _read(PUBLISH_METRICS)
    assert "metrics-kpi-row" in html or "metrics-data-dense" in html
    assert "metrics-sparkline" in html or "sparkline" in html.lower()
    assert 'data-sortable="true"' in html or "sortable" in html.lower()


def test_publish_metrics_css_data_dense_styles():
    css = _read(PUBLISH_METRICS_CSS)
    assert "metrics-kpi" in css or "metrics-data-dense" in css
    assert "metrics-sparkline" in css or "sparkline" in css


def test_publish_metrics_js_supports_table_sorting():
    js = _read(PUBLISH_METRICS_JS)
    assert "sortTable" in js or "data-sort" in js or "sortColumn" in js


# --- 5. Global search ---


def test_global_search_api_route_exists():
    client = _search_client()
    resp = client.get("/api/search", params={"q": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    assert "articles" in data
    assert "published_posts" in data


def test_global_search_script_available_not_mounted_in_sidebar_nav():
    assert GLOBAL_SEARCH_JS.is_file()
    nav = _read(APP_NAV_JS)
    assert "global-search-root" not in nav
    assert "initGlobalSearch" not in nav
    search_js = _read(GLOBAL_SEARCH_JS)
    assert "/api/search" in search_js


# --- 6. Dark mode WCAG contrast polish ---


def test_dark_theme_text_soft_meets_wcag_aa_contrast_target():
    css = _read(DESIGN_TOKENS)
    dark_block = css.split('[data-theme="dark"]')[1]
    match = re.search(r"--color-text-soft:\s*(#[0-9a-fA-F]{6})", dark_block)
    assert match is not None
    hex_color = match.group(1).lower()

    def luminance(hex_rgb: str) -> float:
        channels = [int(hex_rgb[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        return sum(
            (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) * w
            for c, w in zip(channels, (0.2126, 0.7152, 0.0722), strict=True)
        )

    text_lum = luminance(hex_color)
    bg_lum = luminance("#051650")
    lighter, darker = max(text_lum, bg_lum), min(text_lum, bg_lum)
    contrast = (lighter + 0.05) / (darker + 0.05)
    assert contrast >= 4.5, f"contrast {contrast:.2f} for {hex_color} on #051650"
