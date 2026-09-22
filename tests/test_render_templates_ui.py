"""Settings UI: schema-driven render template form + YAML + preview."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_HTML = ROOT / "static" / "settings.html"
SETTINGS_JS = ROOT / "static" / "js" / "settings_render_templates.js"


def test_settings_render_template_yaml_editor():
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    js = SETTINGS_JS.read_text(encoding="utf-8")

    assert 'id="renderTemplateYaml"' in html
    assert "renderTemplateBrand" not in html
    assert "renderTemplateGlyph" not in html
    assert "renderTemplateAccent" not in html
    assert "render_templates.local.yaml" in html
    assert "先复制" in html

    assert "/yaml" in js
    assert "renderTemplateYaml" in js
    assert "renderTemplateBrand" not in js


def test_settings_render_template_preview_hooks():
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    js = SETTINGS_JS.read_text(encoding="utf-8")

    assert 'id="renderTemplatePreview"' in html
    assert "预览短视频" in html
    assert "preview-cover" in js
    assert "preview-video" in js
    assert "1000" in js
    assert "AbortController" in js


def test_settings_render_template_schema_form():
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    js = SETTINGS_JS.read_text(encoding="utf-8")

    assert 'id="renderTemplateForm"' in html
    assert "高级 YAML" in html
    assert "schema" in js
    assert "renderTemplateForm" in js
    assert "widget" in js
    assert "data-path" in js
    assert "scheduleCoverPreview" in js
