import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.ingestion.remotion_render_service import (
    _composition_for_layout,
    _rel_asset_path,
    _stage_asset,
    probe_remotion_runtime,
    remotion_available,
    remotion_project_dir,
    render_with_remotion,
    resolve_npx_argv,
)


def test_resolve_npx_argv_uses_ainews_node_home(tmp_path, monkeypatch):
    node_home = tmp_path / "node"
    node_home.mkdir()
    npx = node_home / "npx.cmd"
    npx.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setenv("AINEWS_NODE_HOME", str(node_home))
    assert resolve_npx_argv()[0] == str(npx)


def test_resolve_npx_argv_defaults_to_npx(monkeypatch):
    monkeypatch.delenv("AINEWS_NODE_HOME", raising=False)
    assert resolve_npx_argv() == ["npx"]


@patch("services.ingestion.remotion_render_service.subprocess.run")
def test_probe_remotion_runtime_updates_marker(mock_run, tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    runtime = data_dir / "runtime"
    runtime.mkdir(parents=True)
    project = runtime / "remotion-project"
    (project / "node_modules").mkdir(parents=True)
    (project / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AINEWS_NODE_HOME", str(tmp_path / "node"))
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.remotion_project_dir",
        lambda: project,
    )
    monkeypatch.setattr(
        "services.ingestion.video_renderer_config.get_data_dir",
        lambda: data_dir,
    )
    mock_run.return_value = MagicMock(returncode=0, stdout="v4.0.0\n", stderr="")

    result = probe_remotion_runtime()
    assert result["success"] is True
    marker_path = runtime / "remotion_v1.json"
    assert marker_path.is_file()
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    assert "last_probe_at" in payload


def test_remotion_project_dir_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "custom_remotion"
    custom.mkdir()
    monkeypatch.setenv("REMOTION_PROJECT_DIR", str(custom))
    assert remotion_project_dir() == custom


def test_composition_for_layout():
    assert _composition_for_layout("chronicle_frame") == "ChronicleVideo"
    assert _composition_for_layout("classic_overlay") == "ClassicOverlayVideo"


def test_stage_static_asset_uses_repo_relative_path(tmp_path, monkeypatch):
    static_img = tmp_path / "static" / "imgs" / "bg.png"
    static_img.parent.mkdir(parents=True)
    static_img.write_bytes(b"png")
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.Config.ROOT_DIR", tmp_path
    )
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.REMOTION_DIR", tmp_path / "remotion"
    )
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.RUNTIME_PUBLIC_DIR",
        tmp_path / "remotion" / "public" / "runtime",
    )
    rel = _rel_asset_path("static/imgs/bg.png", article_id="a1", index=0)
    assert rel == "static/imgs/bg.png"


def test_stage_data_asset_copies_to_runtime(tmp_path, monkeypatch):
    data_img = tmp_path / "data" / "article.jpg"
    data_img.parent.mkdir(parents=True)
    data_img.write_bytes(b"jpg")
    remotion_dir = tmp_path / "remotion"
    public_dir = remotion_dir / "public"
    public_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.Config.ROOT_DIR", tmp_path
    )
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.REMOTION_DIR", remotion_dir
    )
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.RUNTIME_PUBLIC_DIR",
        public_dir / "runtime",
    )
    rel = _stage_asset("/data/article.jpg", article_id="art9", index=1)
    staged = public_dir / rel
    assert staged.is_file()
    assert staged.read_bytes() == b"jpg"


@patch("services.ingestion.remotion_render_service.remotion_available", return_value=False)
def test_render_with_remotion_not_installed(mock_avail):
    result = render_with_remotion(
        article_id="x",
        draft={},
        image_paths=["static/imgs/bg.png"],
        bgm_path="",
        template={"layout_kind": "chronicle_frame"},
    )
    assert result["success"] is False
    assert result["error"] == "remotion_not_installed"


@patch("services.ingestion.remotion_render_service.remotion_available", return_value=True)
@patch("services.ingestion.remotion_render_service.subprocess.run")
def test_render_with_remotion_success(mock_run, mock_avail, tmp_path, monkeypatch):
    remotion_dir = tmp_path / "remotion"
    (remotion_dir / "node_modules").mkdir(parents=True)
    (remotion_dir / "package.json").write_text("{}", encoding="utf-8")
    out_dir = tmp_path / "data" / "videos"
    out_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "services.ingestion.remotion_render_service.Config.ROOT_DIR", tmp_path
    )
    monkeypatch.setenv("REMOTION_PROJECT_DIR", str(remotion_dir))

    def _fake_run(cmd, **kwargs):
        out = Path(cmd[4])
        out.write_bytes(b"mp4")
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _fake_run
    static_img = tmp_path / "static" / "imgs" / "bg.png"
    static_img.parent.mkdir(parents=True)
    static_img.write_bytes(b"png")

    result = render_with_remotion(
        article_id="art1",
        draft={"main_line1": "标题"},
        image_paths=["static/imgs/bg.png", "static/imgs/bg.png"],
        bgm_path="",
        template={"layout_kind": "chronicle_frame", "video": {}},
        durations=[2.0, 2.0],
    )
    assert result["success"] is True
    assert result["renderer"] == "remotion"
    assert result["composition"] == "ChronicleVideo"
