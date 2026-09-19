"""TDD: in-memory template YAML preview does not persist local.yaml."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from PIL import Image

from src.utils.paths import get_data_dir


def _yaml_classic() -> str:
    return yaml.dump(
        {
            "id": "flash_news_portrait",
            "layout_kind": "classic_overlay",
            "canvas": {"width": 1080, "height": 1920},
            "background_image": "static/imgs/bg.png",
        },
        allow_unicode=True,
    )


def test_preview_cover_from_yaml_does_not_write_local(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    get_data_dir.cache_clear()
    local_path = tmp_path / "render_templates.local.yaml"
    monkeypatch.setattr(
        "services.ingestion.render_templates.RENDER_TEMPLATES_LOCAL_PATH", local_path
    )

    def fake_cover(**kwargs):
        out = tmp_path / "cache" / "template-preview" / "cover.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), (10, 20, 30)).save(out, format="JPEG")
        return {"success": True, "cover_path": "cache/template-preview/cover.jpg"}

    monkeypatch.setattr(
        "services.ingestion.template_preview.render_article_cover",
        fake_cover,
    )
    from services.ingestion.template_preview import preview_cover_from_yaml

    result = preview_cover_from_yaml(_yaml_classic())
    assert result["success"] is True
    assert "image_url" in result
    assert not local_path.exists()


def test_preview_cover_from_yaml_rejects_invalid_yaml():
    from services.ingestion.template_preview import preview_cover_from_yaml

    with pytest.raises(ValueError, match="invalid_yaml"):
        preview_cover_from_yaml("id: [\n")


def test_preview_video_from_yaml_uses_python_and_short_min_duration(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    get_data_dir.cache_clear()
    captured: dict = {}

    def fake_video(**kwargs):
        captured.update(kwargs)
        out = tmp_path / "cache" / "template-preview" / "clip.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-mp4")
        return {"success": True, "video_path": "cache/template-preview/clip.mp4"}

    monkeypatch.setattr(
        "services.ingestion.template_preview.render_ingested_video",
        fake_video,
    )
    from services.ingestion.template_preview import preview_video_from_yaml

    result = preview_video_from_yaml(
        "id: demo\nlayout_kind: chronicle_frame\nvideo:\n  min_duration_sec: 8\n"
    )
    assert result["success"] is True
    assert "video_url" in result
    assert captured["renderer"] == "python"
    assert float(captured["template"]["video"]["min_duration_sec"]) == 3
    assert not (tmp_path / "render_templates.local.yaml").exists()
