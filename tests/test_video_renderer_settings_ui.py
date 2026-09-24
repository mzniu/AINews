"""Settings UI: video renderer (Remotion / Python) preferences."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_HTML = ROOT / "static" / "settings.html"
SETTINGS_JS = ROOT / "static" / "js" / "settings_video_renderer.js"
RENDER_JS = ROOT / "static" / "js" / "settings_render_templates.js"
TABS_JS = ROOT / "static" / "js" / "settings_tabs.js"


def test_settings_video_renderer_panel_and_hooks():
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    js = SETTINGS_JS.read_text(encoding="utf-8")

    assert 'data-tab="video-renderer"' in html
    assert 'id="panel-video-renderer"' in html
    assert "成片引擎" in html
    assert 'id="videoRendererPreferred"' in html
    assert 'id="videoRendererAllowFallback"' in html
    assert 'id="videoRendererInstallBlock"' in html
    assert "desktop_runtime.local.yaml" in html

    assert "/api/runtime/video-renderer" in js
    assert "loadVideoRendererSettings" in js
    assert "repair_hint" in js
    assert "allow_python_fallback" in js
    assert "__TAURI__" in js
    assert "remotion_setup_run" in js
    assert "ainews:remotion-setup-progress" in js


def test_settings_tabs_loads_video_renderer():
    js = TABS_JS.read_text(encoding="utf-8")
    assert "video-renderer" in js
    assert "loadVideoRendererSettings" in js


def test_render_templates_panel_shows_engine_banner():
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    js = RENDER_JS.read_text(encoding="utf-8")

    assert 'id="renderTemplateEngineBanner"' in html
    assert "refreshRenderTemplateEngineBanner" in js
    assert "/api/runtime/video-renderer" in js
