import pytest

from services.publishing.path_guard import PathGuardError, resolve_video_path
from src.utils.config import Config


def test_resolve_video_path_accepts_data_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    video_dir = tmp_path / "data" / "videos"
    video_dir.mkdir(parents=True)
    video = video_dir / "a.mp4"
    video.write_bytes(b"\x00")
    resolved = resolve_video_path("/data/videos/a.mp4")
    assert resolved == video.resolve()


def test_resolve_video_path_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    (tmp_path / "data" / "videos").mkdir(parents=True)
    with pytest.raises(PathGuardError):
        resolve_video_path("../../etc/passwd")
