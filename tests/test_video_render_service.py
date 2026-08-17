from unittest.mock import patch

from services.ingestion.video_render_service import render_ingested_video, resolve_ingested_clip_durations


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
def test_render_ingested_video_allows_single_image(mock_chronicle):
    mock_chronicle.return_value = {"success": True, "video_path": "/data/videos/one.mp4"}
    result = render_ingested_video(
        article_id="art1",
        draft={"main_line1": "突发！单图"},
        image_paths=["/data/a.jpg"],
        bgm_path="static/music/a.mp3",
        template={"layout_kind": "chronicle_frame", "canvas": {"fps": 24}, "video": {"fallback_clip_sec": 7.0}},
    )
    assert result["success"] is True
    mock_chronicle.assert_called_once()
    assert mock_chronicle.call_args.kwargs["image_paths"] == ["/data/a.jpg"]
    assert mock_chronicle.call_args.kwargs["durations"] == [7.0]
