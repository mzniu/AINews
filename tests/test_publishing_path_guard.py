import pytest

from services.publishing.path_guard import PathGuardError, resolve_video_path


def test_resolve_video_path_accepts_data_videos(tmp_path, monkeypatch):
    from src.utils import paths

    data_dir = tmp_path / "data"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    paths.get_data_dir.cache_clear()
    video_dir = data_dir / "videos"
    video_dir.mkdir(parents=True)
    video = video_dir / "a.mp4"
    video.write_bytes(b"\x00")
    resolved = resolve_video_path("/data/videos/a.mp4")
    assert resolved == video.resolve()


def test_resolve_video_path_rejects_escape(tmp_path, monkeypatch):
    from src.utils import paths

    data_dir = tmp_path / "data"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    paths.get_data_dir.cache_clear()
    (data_dir / "videos").mkdir(parents=True)
    with pytest.raises(PathGuardError):
        resolve_video_path("../../etc/passwd")
