from unittest.mock import patch

from services.ingestion.video_render_service import (
    render_ingested_video,
    resolve_ingested_clip_durations,
    resolve_video_renderer,
)
from services.ingestion.video_renderer_config import save_desktop_runtime_config


def test_resolve_ingested_clip_durations_two_images():
    assert resolve_ingested_clip_durations(2) == [3.5, 3.5]


def test_resolve_ingested_clip_durations_three_images():
    assert resolve_ingested_clip_durations(3) == [2.5, 3.0, 3.0]


def test_resolve_ingested_clip_durations_four_images():
    assert resolve_ingested_clip_durations(4) == [2.0, 2.0, 2.0, 2.0]


def test_resolve_ingested_clip_durations_five_images_repeats_gte_rule():
    assert resolve_ingested_clip_durations(5) == [2.0, 2.0, 2.0, 2.0, 2.0]


def test_resolve_ingested_clip_durations_one_image_uses_table_or_fallback():
    assert resolve_ingested_clip_durations(1) == [7.0]


def test_resolve_ingested_clip_durations_empty():
    assert resolve_ingested_clip_durations(0) == []
    assert resolve_ingested_clip_durations(-1) == []


def test_resolve_ingested_clip_durations_reads_custom_template_table():
    template = {
        "video": {
            "clip_durations_by_count": {2: [1.0, 2.0]},
            "clip_sec_when_at_least": {"count": 4, "sec": 9.0},
            "fallback_clip_sec": 4.0,
        }
    }
    assert resolve_ingested_clip_durations(2, template=template) == [1.0, 2.0]
    assert resolve_ingested_clip_durations(1, template=template) == [4.0]
    assert resolve_ingested_clip_durations(4, template=template) == [9.0, 9.0, 9.0, 9.0]


@patch("services.ingestion.chronicle_render.render_chronicle_video")
@patch("services.ingestion.render_image_utils.is_renderable_local_image", return_value=True)
def test_render_ingested_video_allows_single_image(mock_renderable, mock_chronicle):
    mock_chronicle.return_value = {"success": True, "video_path": "/data/videos/one.mp4"}
    result = render_ingested_video(
        article_id="art1",
        draft={"main_line1": "突发！单图"},
        image_paths=["/data/a.jpg"],
        bgm_path="static/music/a.mp3",
        template={"layout_kind": "chronicle_frame", "canvas": {"fps": 24}, "video": {"fallback_clip_sec": 7.0}},
        renderer="python",
    )
    assert result["success"] is True
    mock_chronicle.assert_called_once()
    assert mock_chronicle.call_args.kwargs["image_paths"] == ["data/a.jpg"]
    assert mock_chronicle.call_args.kwargs["durations"] == [8.0]


def test_resolve_video_renderer_defaults_to_remotion(monkeypatch):
    monkeypatch.delenv("VIDEO_RENDERER", raising=False)
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.remotion_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.is_packaged",
        lambda: False,
    )
    assert resolve_video_renderer() == "remotion"
    assert resolve_video_renderer(None) == "remotion"


def test_resolve_video_renderer_python_override(monkeypatch):
    monkeypatch.setenv("VIDEO_RENDERER", "python")
    assert resolve_video_renderer() == "python"
    assert resolve_video_renderer("remotion") == "remotion"


def test_resolve_video_renderer_packaged_auto_falls_back_to_python(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.CONFIG_PATH",
        config_dir / "desktop_runtime.local.yaml",
    )
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.is_packaged",
        lambda: True,
    )
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.remotion_available",
        lambda: False,
    )
    monkeypatch.delenv("VIDEO_RENDERER", raising=False)
    assert resolve_video_renderer() == "python"


@patch("services.ingestion.render_image_utils.is_renderable_local_image", return_value=True)
@patch("services.ingestion.chronicle_render.render_chronicle_video")
def test_render_ingested_video_blocks_when_remotion_required_not_ready(
    mock_chronicle, mock_renderable, monkeypatch, tmp_path
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.CONFIG_PATH",
        config_dir / "desktop_runtime.local.yaml",
    )
    save_desktop_runtime_config({"preferred": "remotion", "allow_python_fallback": False})
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.remotion_available",
        lambda: False,
    )
    result = render_ingested_video(
        article_id="art1",
        draft={"main_line1": "标题"},
        image_paths=["/data/a.jpg"],
        bgm_path="static/music/a.mp3",
        template={"layout_kind": "chronicle_frame"},
    )
    assert result["success"] is False
    assert result["error"] == "remotion_not_ready"
    mock_chronicle.assert_not_called()


@patch("services.ingestion.render_image_utils.is_renderable_local_image", return_value=True)
@patch("services.ingestion.remotion_render_service.render_with_remotion")
@patch("services.ingestion.chronicle_render.render_chronicle_video")
def test_render_ingested_video_no_fallback_on_remotion_failure(
    mock_chronicle, mock_remotion, mock_renderable, monkeypatch, tmp_path
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.CONFIG_PATH",
        config_dir / "desktop_runtime.local.yaml",
    )
    save_desktop_runtime_config({"preferred": "remotion", "allow_python_fallback": False})
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.remotion_available",
        lambda: True,
    )
    mock_remotion.return_value = {"success": False, "error": "remotion_render_failed"}
    result = render_ingested_video(
        article_id="art1",
        draft={"main_line1": "标题"},
        image_paths=["/data/a.jpg"],
        bgm_path="static/music/a.mp3",
        template={"layout_kind": "chronicle_frame"},
    )
    assert result["success"] is False
    assert result["error"] == "remotion_render_failed"
    mock_chronicle.assert_not_called()
