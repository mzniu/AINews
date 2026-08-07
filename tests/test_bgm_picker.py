"""Tests for random BGM selection."""
from __future__ import annotations

from pathlib import Path

from services.ingestion.bgm_picker import pick_random_bgm


def test_pick_random_bgm_from_dir(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "a.mp3").write_bytes(b"fake")
    (music_dir / "b.mp3").write_bytes(b"fake2")
    path = pick_random_bgm(music_dir, rng=lambda seq: seq[0])
    assert path.endswith("a.mp3") or path.endswith("b.mp3")


def test_pick_random_bgm_fallback_when_empty(tmp_path):
    path = pick_random_bgm(tmp_path / "empty")
    assert path == "static/music/background.mp3"
