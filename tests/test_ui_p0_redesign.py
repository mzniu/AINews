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

PAGE_TITLE_H1_PAGES = APP_PAGES + [
    "video_maker.html",
    "video_editor3.html",
    "github_video_maker.html",
    "digital_human.html",
    "model_settings.html",
    "publish_queue.html",
    "publish_metrics.html",
    "publish_comments.html",
    "publish_accounts.html",
    "candidate_pool.html",
]

# Common pictographs / emoji in legacy page titles (not exhaustive Unicode emoji blocks).
_PAGE_TITLE_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"
    r"|⚙|🌐|📹|🚀|⚠|🎬|📝|🖼|🤖|💡|🏠|⬆|🗑|✨|❄|⬇|🎞|👁|▶|⏸|✏|✂️|🅰|↩|↔|🎯|🏷|✍|🎙|🕷|📊|🎥"
)


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
        "icon-github",
        "icon-user",
        "icon-scrape",
        "icon-send",
        "icon-settings",
    ):
        assert f'id="{icon_id}"' in svg


def test_settings_icon_is_gear_not_sun_rays():
    svg = _read(SPRITES)
    settings = svg.split('id="icon-settings"', 1)[1].split("</symbol>", 1)[0]
    assert "M12.22 2h" in settings
    assert "M12 1v2" not in settings


def test_sprites_have_sidebar_collapse_and_expand_icons():
    svg = _read(SPRITES)
    assert 'id="icon-sidebar-collapse"' in svg
    assert 'id="icon-sidebar-expand"' in svg


def test_nav_collapse_button_uses_sidebar_icons_not_settings():
    js = _read(APP_NAV_JS)
    idx = js.find("app-nav-collapse")
    assert idx != -1
    snippet = js[idx : idx + 320]
    assert "sidebar-collapse" in snippet
    assert "navIcon('settings')" not in snippet
    assert "sidebar-expand" in js


def test_app_nav_js_uses_sprite_not_emoji_nav():
    js = _read(APP_NAV_JS)
    assert "sprites.svg" in js or "icon-home" in js
    assert "工作台" in js
    assert "内容抓取" in js
    assert "icon: 'github'" in js
    assert "icon: 'user'" in js
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
    assert "theme-toggle-btn" in js
    assert 'data-theme-set="light"' in js


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


def test_app_nav_publish_group_has_standalone_entries():
    js = _read(APP_NAV_JS)
    publish_section = re.search(r"label:\s*['\"]发布中心['\"].*?items:\s*\[(.*?)\]", js, re.S)
    assert publish_section is not None
    items = publish_section.group(1)
    assert "发布设置" in items
    assert "账号绑定" in items
    assert "发布队列" in items
    assert "已发布数据" in items
    assert "评论管理" in items
    assert "候选池" in items


def test_publish_center_is_settings_page_not_tab_hub():
    html = _read(PUBLISH_CENTER)
    assert "hub-tab" not in html
    assert "publish_hub.js" not in html
    assert "发布策略灰度" in html
    assert "快速发布" in html


def test_embed_pages_hide_nav_in_iframe():
    embed_js = _read(STATIC / "js" / "shared" / "embed.js")
    shell_css = _read(STATIC / "css" / "app_shell.css")
    assert 'data-embed' in embed_js
    assert "document.documentElement.setAttribute('data-embed', '1')" in embed_js
    assert 'html[data-embed="1"]' in shell_css
    for page in ("publish_queue.html", "publish_metrics.html", "publish_comments.html", "candidate_pool.html"):
        html = _read(STATIC / page)
        assert "embed.js" in html


def test_candidate_pool_reason_labels_are_human_readable():
    js = _read(STATIC / "js" / "candidate_pool.js")
    assert "recommend.publish.wechat_dual_grade" in js
    assert "视频号行业与传播评分均达标" in js
    assert "policy.disabled.platform" in js
    assert "该平台在策略中未启用" in js
    assert "formatReasonLabel" in js


def test_publish_routes_serve_standalone_pages():
    client = _main_routes_client()
    pages = {
        "/publish-queue": "发布队列",
        "/publish-metrics": "已发布数据",
        "/publish-comments": "评论管理",
        "/candidate-pool": "候选池",
        "/publish-accounts": "账号绑定",
    }
    for path, title in pages.items():
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 200
        assert title in resp.text


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


@pytest.mark.parametrize("page", PAGE_TITLE_H1_PAGES)
def test_page_document_title_and_h1_have_no_emoji(page: str):
    html = _read(STATIC / page)
    title_match = re.search(r"<title>([^<]+)</title>", html)
    assert title_match is not None, f"{page} missing <title>"
    assert not _PAGE_TITLE_EMOJI_RE.search(title_match.group(1)), f"{page} <title> has emoji"
    for h1_text in re.findall(r"<h1[^>]*>([^<]+)</h1>", html):
        assert not _PAGE_TITLE_EMOJI_RE.search(h1_text), f"{page} <h1> has emoji: {h1_text!r}"


def test_dashboard_loads_shared_ui_and_theme():
    html = _read(DASHBOARD_HTML)
    assert "theme.js" in html
    assert "ui.js" in html


@pytest.mark.parametrize("page", APP_PAGES)
def test_app_pages_load_theme_script(page: str):
    html = _read(STATIC / page)
    assert "theme.js" in html


def test_dashboard_hot_radar_uses_ingestion_api():
    js = _read(STATIC / "js" / "dashboard.js")
    assert "/api/ingestion/hot-radar" in js
    assert "/api/hot-radar/snapshots" not in js


def test_light_theme_shell_tokens_use_dark_readable_text():
    tokens = _read(DESIGN_TOKENS)
    shell = _read(STATIC / "css" / "app_shell.css")
    assert "--shell-heading: var(--color-text);" in tokens
    assert "--app-off-white: var(--shell-heading);" in shell
    assert "--shell-input-bg: var(--color-surface-raised);" in tokens
    assert ':root:not([data-theme="dark"])' in tokens
    assert "--nav-width: 224px;" in tokens
    dark_start = tokens.index('[data-theme="dark"]')
    root_nav = tokens.index("--nav-width: 224px;")
    assert root_nav < dark_start, "nav layout tokens must live in shared :root for dark theme"


def test_theme_script_sets_data_theme_on_toggle():
    js = _read(THEME_JS)
    assert "setAttribute('data-theme'" in js
    assert "ainews-theme" in js
