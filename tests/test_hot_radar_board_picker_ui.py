"""Settings UI: pick TopHub boards by name instead of typing hashid."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_HTML = ROOT / "static" / "settings.html"
SETTINGS_JS = ROOT / "static" / "js" / "settings_hot_radar.js"
APP_SHELL_CSS = ROOT / "static" / "css" / "app_shell.css"


def test_settings_hot_radar_picker_copy_and_hooks():
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    js = SETTINGS_JS.read_text(encoding="utf-8")
    css = APP_SHELL_CSS.read_text(encoding="utf-8")

    assert "添加热榜" in html
    assert "已选热榜" in html
    assert "TopHub 的一个 hashid" not in html

    assert 'data-field="hashid"' not in js
    assert 'data-field="id"' not in js
    assert "/api/ingestion/hot-radar/nodes" in js
    assert "从当前行业移除" in js
    assert "board_${Date.now()}" not in js

    assert "app-modal--wide" in css
    assert "app-modal--wide" in js or "app-modal--wide" in html
