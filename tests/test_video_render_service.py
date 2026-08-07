from services.ingestion.video_render_service import resolve_ingested_clip_durations


def test_resolve_ingested_clip_durations_two_images():
    assert resolve_ingested_clip_durations(2) == [3.5, 3.5]


def test_resolve_ingested_clip_durations_three_images():
    assert resolve_ingested_clip_durations(3) == [2.5, 3.0, 3.0]


def test_resolve_ingested_clip_durations_four_images():
    assert resolve_ingested_clip_durations(4) == [2.0, 2.0, 2.0, 2.0]
