"""P0 UI/UX redesign — design tokens, routing, theme, nav, publish hub."""

from __future__ import annotations

import re
from pathlib import Path

import importlib.util
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
DESIGN_TOKENS = STATIC / "css" / "design-system" / "tokens.css"
FONTS_CSS = STATIC / "css" / "design-system" / "fonts.css"
SPRITES = STATIC / "icons" / "sprites.svg"
THEME_JS = STATIC / "js" / "shared" / "theme.js"
UI_JS = STATIC / "js" / "shared" / "ui.js"
APP_NAV_JS = STATIC / "js" / "shared" / "app_nav.js"
DASHBOARD_HTML = STATIC / "dashboard.html"
SCRAPE_HTML = STATIC / "scrape.html"
AUTH_HTML = STATIC / "auth.html"
PUBLISH_CENTER = STATIC / "publish_center.html"

FONT_FILES = [
    "newsreader-600.ttf",
    "newsreader-700.ttf",
    "roboto-400.ttf",
    "roboto-500.ttf",
]

APP_PAGES = [
    "dashboard.html",
    "scrape.html",
    "ingestion_library.html",
    "hot_radar.html",
    "publish_center.html",
    "settings.html",
]


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


# --- 1. Design tokens ---


def test_design_system_tokens_file_exists_with_light_and_dark():
    css = _read(DESIGN_TOKENS)
    assert ":root" in css or '[data-theme="light"]' in css
    assert '[data-theme="dark"]' in css
    assert "--color-brand-vibrant: #123499" in css
    assert "--color-bg-solid" in css


def test_legacy_tokens_css_imports_design_system():
    css = _read(STATIC / "css" / "tokens.css")
    assert "design-system/tokens.css" in css


def test_app_shell_references_design_tokens():
    css = _read(STATIC / "css" / "app_shell.css")
    assert "design-system/tokens.css" in css or "var(--color-" in css


# --- 2. Offline fonts ---


@pytest.mark.parametrize("filename", FONT_FILES)
def test_offline_font_files_exist(filename: str):
    assert (STATIC / "fonts" / filename).is_file()


def test_fonts_css_declares_newsreader_and_roboto():
    css = _read(FONTS_CSS)
    assert "Newsreader" in css
    assert "Roboto" in css
    assert "/static/fonts/" in css


def test_app_shell_loads_offline_fonts():
    css = _read(STATIC / "css" / "app_shell.css")
    assert "design-system/fonts.css" in css


# --- 3. SVG sprite ---


def test_sprites_svg_contains_nav_icons():
    svg = _read(SPRITES)
    for icon_id in (
        "icon-home",
        "icon-library",
        "icon-radar",
        "icon-film",
        "icon-scrape",
        "icon-send",
        "icon-settings",
    ):
        assert f'id="{icon_id}"' in svg


def test_app_nav_js_uses_sprite_not_emoji_nav():
    js = _read(APP_NAV_JS)
    assert "sprites.svg" in js or "icon-home" in js
    assert "工作台" in js
    assert "内容抓取" in js
    # Nav labels should not rely on emoji as primary icons
    assert "🌐" not in js


# --- 4. Theme toggle ---


def test_theme_js_persists_to_local_storage():
    js = _read(THEME_JS)
    assert "localStorage" in js
    assert "data-theme" in js
    assert "light" in js


def test_theme_js_default_is_light():
    js = _read(THEME_JS)
    assert re.search(r"return\s+['\"]light['\"]", js) or "defaultTheme" in js and "'light'" in js


def test_app_nav_includes_theme_toggle():
    js = _read(APP_NAV_JS)
    assert "theme-toggle" in js or "Theme" in js


# --- 5. Auth alignment ---


def test_auth_html_uses_light_brand_without_xiaoniu_subtitle():
    html = _read(AUTH_HTML)
    assert "小牛聊AI" not in html
    assert "AINews" in html
    assert "design-system/tokens.css" in html or "123499" in html


def test_auth_html_loads_theme_script():
    html = _read(AUTH_HTML)
    assert "theme.js" in html


# --- 6. Dashboard home ---


def test_root_route_serves_dashboard():
    client = _main_routes_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "工作台" in resp.text or "pipeline" in resp.text.lower()
    assert "网页内容抓取工具" not in resp.text


def test_dashboard_html_has_pipeline_and_metrics():
    html = _read(DASHBOARD_HTML)
    assert "pipeline" in html.lower()
    assert "metric" in html.lower() or "metrics" in html.lower()
    assert "快捷" in html


def test_dashboard_page_title_format():
    html = _read(DASHBOARD_HTML)
    assert re.search(r"<title>AINews · 工作台</title>", html)


# --- 7. Scrape migration ---


def test_scrape_route_exists():
    client = _main_routes_client()
    resp = client.get("/scrape")
    assert resp.status_code == 200
    assert "内容抓取" in resp.text or "抓取" in resp.text


def test_scrape_html_exists_with_fetch_controls():
    html = _read(SCRAPE_HTML)
    assert 'id="urlInput"' in html
    assert 'id="fetchBtn"' in html


def test_scrape_page_title_format():
    html = _read(SCRAPE_HTML)
    assert re.search(r"<title>AINews · 内容抓取</title>", html)


# --- 8. Publish Tab Hub ---


def test_app_nav_publish_group_only_publish_center():
    js = _read(APP_NAV_JS)
    dist_section = re.search(r"label:\s*['\"]分发['\"].*?items:\s*\[(.*?)\]", js, re.S)
    assert dist_section is not None
    items = dist_section.group(1)
    assert "发布中心" in items
    assert "发布队列" not in items
    assert "已发布数据" not in items
    assert "评论管理" not in items
    assert "候选池" not in items


def test_publish_center_is_tab_hub():
    html = _read(PUBLISH_CENTER)
    assert "publish-hub" in html.lower() or "tab-hub" in html.lower() or "hub-tab" in html.lower()
    for label in ("账号", "队列", "已发布", "评论", "候选"):
        assert label in html


def test_publish_legacy_routes_redirect_or_hub():
    client = _main_routes_client()
    for path in ("/publish-queue", "/publish-metrics", "/publish-comments", "/candidate-pool"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (200, 307, 308, 302)
        if resp.status_code == 200:
            body = resp.text
            assert "publish-hub" in body.lower() or "hub-tab" in body.lower() or "tab=" in path


# --- 9. Unified Banner / Modal / Toast ---


def test_shared_ui_js_exports_toast_modal_banner():
    js = _read(UI_JS)
    assert "showToast" in js
    assert "openModal" in js
    assert "AppBanner" in js or "showBanner" in js


def test_app_shell_has_app_banner_styles():
    css = _read(STATIC / "css" / "app_shell.css")
    assert "app-banner" in css or "app-toast" in css


# --- 10. Page titles ---


@pytest.mark.parametrize("page", APP_PAGES)
def test_app_page_titles_use_ainews_prefix(page: str):
    html = _read(STATIC / page)
    assert re.search(r"<title>AINews · .+</title>", html), f"{page} missing AINews title format"


def test_dashboard_loads_shared_ui_and_theme():
    html = _read(DASHBOARD_HTML)
    assert "theme.js" in html
    assert "ui.js" in html
