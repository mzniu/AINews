"""P2 UI/UX redesign — sidebar collapse, metrics charts/export, library thumbnails, design system."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
APP_NAV_JS = STATIC / "js" / "shared" / "app_nav.js"
APP_SHELL_CSS = STATIC / "css" / "app_shell.css"
DESIGN_TOKENS = STATIC / "css" / "design-system" / "tokens.css"
PUBLISH_METRICS = STATIC / "publish_metrics.html"
PUBLISH_METRICS_CSS = STATIC / "css" / "publish_metrics.css"
PUBLISH_METRICS_JS = STATIC / "js" / "publish_center_metrics.js"
INGESTION_LIBRARY_JS = STATIC / "js" / "ingestion_library.js"
INGESTION_LIBRARY_CSS = STATIC / "css" / "ingestion_library.css"
HOT_RADAR_JS = STATIC / "js" / "hot_radar.js"
DESIGN_SYSTEM_HTML = STATIC / "design-system.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _main_routes_client() -> TestClient:
    path = ROOT / "api" / "routes" / "main_routes.py"
    spec = importlib.util.spec_from_file_location("main_routes", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


def _publishing_client() -> TestClient:
    from src.db.engine import init_db

    init_db()
    path = ROOT / "api" / "routes" / "publishing_routes.py"
    spec = importlib.util.spec_from_file_location("publishing_routes", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


# --- 1. Sidebar collapse + top bar mode ---


def test_app_nav_has_sidebar_collapse_toggle():
    js = _read(APP_NAV_JS)
    assert "nav-collapse" in js or "navCollapse" in js or "sidebar-collapse" in js
    assert "localStorage" in js
    assert re.search(r"nav-collapsed|data-nav-collapsed", js + _read(APP_SHELL_CSS))
    assert "nav-top-bar" not in js or "classList.toggle('nav-top-bar'" not in js


def test_app_shell_css_has_collapsed_nav_and_top_bar_modes():
    css = _read(APP_SHELL_CSS)
    tokens = _read(DESIGN_TOKENS)
    assert "--nav-width-collapsed" in tokens or "64px" in css
    assert re.search(r"\.nav-collapsed|body\.nav-collapsed|\[data-nav-collapsed", css)
    assert re.search(r"nav-top-bar|top-bar-mode|nav-topbar", css)


def test_app_nav_js_exposes_collapse_helpers():
    js = _read(APP_NAV_JS)
    assert "AppNav" in js
    assert re.search(r"toggleNavCollapse|setNavCollapsed|navCollapsed", js)


# --- 2. Publish metrics charts + export ---


def test_publish_metrics_has_platform_trend_charts_section():
    html = _read(PUBLISH_METRICS)
    assert "metrics-charts" in html or "metricsCharts" in html
    css = _read(PUBLISH_METRICS_CSS)
    assert "metrics-chart" in css


def test_publish_metrics_js_renders_summary_charts():
    js = _read(PUBLISH_METRICS_JS)
    assert re.search(r"renderMetricsCharts|drawMetricsChart|renderPlatformCharts", js)
    assert re.search(r"canvas|svg", js, re.I)


def test_publish_metrics_has_json_export_button():
    html = _read(PUBLISH_METRICS)
    js = _read(PUBLISH_METRICS_JS)
    assert "metricsExportJsonBtn" in html or "导出 JSON" in html
    assert re.search(r"exportMetricsJson|export.*json", js, re.I)


def test_published_posts_json_export_api():
    client = _publishing_client()
    resp = client.get("/api/publishing/published-posts/export.json", params={"days": 30})
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/json")
    data = resp.json()
    assert data.get("success") is True
    assert "posts" in data


# --- 3. Ingestion library thumbnails + hot radar linkage ---


def test_ingestion_library_article_rows_include_grade_color_bar():
    js = _read(INGESTION_LIBRARY_JS)
    css = _read(INGESTION_LIBRARY_CSS)
    assert "grade-bar" in js or "article-grade-bar" in js
    assert re.search(r"grade-bar|article-grade-bar", css)


def test_ingestion_library_selected_row_uses_light_text_on_deep_panel():
    css = _read(INGESTION_LIBRARY_CSS)
    assert ".article-item.selected" in css
    assert "--selected-row-text" in css
    assert "font-weight-bold" in css and "article-item.selected" in css
    assert "text-muted" in css and "article-item.selected" in css


def test_ingestion_library_selected_row_badges_use_high_contrast_tokens():
    css = _read(INGESTION_LIBRARY_CSS)
    assert "--selected-badge-info-text" in css
    assert re.search(r"article-item\.selected.*badge-success|badge-success.*article-item\.selected", css)
    assert re.search(r"article-item\.selected.*badge-light|badge-light.*article-item\.selected", css)
    assert re.search(r"article-item\.selected.*badge-published|badge-published.*article-item\.selected", css)


def test_ingestion_library_highlights_hot_radar_deeplink():
    js = _read(INGESTION_LIBRARY_JS)
    assert re.search(r"hot-radar|hot_radar|from=hot-radar", js)
    assert re.search(r"highlight-hot|hot-radar-highlight|article-hot-highlight", js + _read(INGESTION_LIBRARY_CSS))


def test_ingestion_library_article_detail_has_playbook_rank_preview():
    js = _read(INGESTION_LIBRARY_JS)
    assert "playbookRankPreviewBtn" in js
    assert "/api/copy-agent/rank-preview" in js
    assert "runPlaybookRankPreview" in js


def test_hot_radar_hot_list_links_to_ingestion_library():
    js = _read(HOT_RADAR_JS)
    assert "/ingestion-library?article_id=" in js
    assert re.search(r"matched_article_id|article_id|library-link", js)


# --- 4. Design system Storybook ---


def test_design_system_static_page_exists():
    assert DESIGN_SYSTEM_HTML.is_file()
    html = _read(DESIGN_SYSTEM_HTML)
    assert "AINews Design System" in html or "设计系统" in html
    assert re.search(r"btn|soft-card|badge", html)


def test_design_system_route_served():
    client = _main_routes_client()
    resp = client.get("/design-system")
    assert resp.status_code == 200
    assert "设计系统" in resp.text or "Design System" in resp.text
