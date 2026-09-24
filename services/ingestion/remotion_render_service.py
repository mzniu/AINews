"""Remotion-based video renderer (parallel path to Python/MoviePy pipeline)."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.utils.config import Config

DEFAULT_COVER_INTRO_SEC = 1.0


def remotion_project_dir() -> Path:
    raw = os.environ.get("REMOTION_PROJECT_DIR")
    if raw and str(raw).strip():
        return Path(str(raw).strip())
    return Config.ROOT_DIR / "remotion"


def runtime_public_dir() -> Path:
    return remotion_project_dir() / "public" / "runtime"


# Kept for tests that monkeypatch module-level paths.
REMOTION_DIR = Config.ROOT_DIR / "remotion"
RUNTIME_PUBLIC_DIR = REMOTION_DIR / "public" / "runtime"


def remotion_available() -> bool:
    """Return True when Remotion dependencies are installed."""
    root = remotion_project_dir()
    return (root / "package.json").is_file() and (root / "node_modules").is_dir()


def resolve_npx_argv() -> list[str]:
    """Prefer portable Node from desktop shell (`AINEWS_NODE_HOME`)."""
    raw = os.environ.get("AINEWS_NODE_HOME")
    if raw and str(raw).strip():
        home = Path(str(raw).strip())
        if os.name == "nt":
            candidate = home / "npx.cmd"
        else:
            candidate = home / "bin" / "npx"
        if candidate.is_file():
            return [str(candidate)]
    return ["npx"]


def _node_executable() -> str | None:
    raw = os.environ.get("AINEWS_NODE_HOME")
    if not raw or not str(raw).strip():
        return None
    home = Path(str(raw).strip())
    if os.name == "nt":
        candidate = home / "node.exe"
    else:
        candidate = home / "bin" / "node"
    return str(candidate) if candidate.is_file() else None


def probe_remotion_runtime(timeout_sec: float = 10.0) -> dict[str, Any]:
    """Run lightweight Node/Remotion probes and refresh marker timestamp."""
    from services.ingestion.video_renderer_config import load_remotion_marker, remotion_marker_path

    if not remotion_available():
        return {"success": False, "error": "remotion_not_installed"}

    node = _node_executable()
    env = os.environ.copy()
    project = remotion_project_dir()
    if node:
        node_dir = str(Path(node).parent)
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

    node_version: str | None = None
    try:
        if node:
            node_proc = subprocess.run(
                [node, "-v"],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                env=env,
            )
            if node_proc.returncode != 0:
                return {"success": False, "error": "node_probe_failed", "stderr": node_proc.stderr}
            if node_proc.stdout.strip():
                node_version = node_proc.stdout.strip()
        npx = resolve_npx_argv()
        remotion_proc = subprocess.run(
            [*npx, "remotion", "versions"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            env=env,
        )
        if remotion_proc.returncode != 0:
            return {
                "success": False,
                "error": "remotion_probe_failed",
                "stderr": remotion_proc.stderr[-2000:],
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "remotion_probe_timeout"}
    except OSError as exc:
        return {"success": False, "error": f"remotion_probe_spawn_failed: {exc}"}

    marker = load_remotion_marker() or {"install_id": "remotion_v1"}
    marker["last_probe_at"] = datetime.now(timezone.utc).isoformat()
    if node_version:
        marker["node_version"] = node_version

    path = remotion_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "marker": marker}


def _composition_for_layout(layout_kind: str) -> str:
    if layout_kind == "chronicle_frame":
        return "ChronicleVideo"
    return "ClassicOverlayVideo"


def _cover_intro_sec(template: dict[str, Any] | None) -> float:
    video_cfg = (template or {}).get("video") or {}
    if not video_cfg.get("prepend_cover_intro", True):
        return 0.0
    if video_cfg.get("cover_intro_duration_sec") is not None:
        try:
            return max(0.0, float(video_cfg["cover_intro_duration_sec"]))
        except (TypeError, ValueError):
            pass
    # Match media_pipeline default (1.0s); template cover_intro_frames is not sub-second.
    return DEFAULT_COVER_INTRO_SEC


def _maybe_render_cover(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    template: dict[str, Any],
) -> str:
    cover_cfg = template.get("cover") or {}
    if not cover_cfg.get("enabled", True):
        return ""
    if not image_paths:
        return ""
    from services.ingestion.chronicle_render import render_chronicle_cover

    result = render_chronicle_cover(
        article_id=article_id,
        draft=draft,
        image_path=image_paths[0],
        template=template,
    )
    if not result.get("success"):
        return ""
    return str(result.get("cover_path") or "")


def _build_chronicle_props(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    durations: list[float],
    bgm_path: str,
    template: dict[str, Any],
    cover_image_path: str = "",
) -> dict[str, Any]:
    images = []
    for index, path in enumerate(image_paths):
        duration = float(durations[index]) if index < len(durations) else 2.5
        rel_path = _rel_asset_path(path, article_id=article_id, index=index)
        images.append({"path": rel_path, "duration": duration})
    intro_sec = _cover_intro_sec(template) if cover_image_path else 0.0
    return {
        "articleId": article_id,
        "draft": draft,
        "images": images,
        "audioPath": _rel_asset_path(bgm_path, article_id=article_id, index=99) if bgm_path else "",
        "template": template,
        "seed": article_id,
        "coverImagePath": _rel_asset_path(cover_image_path, article_id=article_id, index=200)
        if cover_image_path
        else "",
        "coverIntroDurationSec": intro_sec,
    }


def _build_classic_props(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    durations: list[float],
    bgm_path: str,
    background_image: str,
    template: dict[str, Any] | None,
    cover_image_path: str = "",
) -> dict[str, Any]:
    typo = (template or {}).get("typography") or {}
    video_cfg = (template or {}).get("video") or {}
    images = []
    for index, path in enumerate(image_paths):
        duration = float(durations[index]) if index < len(durations) else 2.5
        images.append(
            {"path": _rel_asset_path(path, article_id=article_id, index=index), "duration": duration}
        )
    intro_sec = _cover_intro_sec(template) if cover_image_path else 0.0
    return {
        "summary": draft.get("summary") or "",
        "main_line1": draft.get("main_line1") or "",
        "main_line2": draft.get("main_line2") or "",
        "subtitle": draft.get("sub_title") or "",
        "subtitle2": draft.get("sub_title2") or "",
        "images": images,
        "audioPath": _rel_asset_path(bgm_path, article_id=article_id, index=99) if bgm_path else "",
        "backgroundImagePath": _rel_asset_path(background_image, article_id=article_id, index=100),
        "tags": draft.get("tags") or "",
        "summaryHighlightKeywords": draft.get("highlight_keywords") or [],
        "showSummary": bool(video_cfg.get("show_summary", True)),
        "titleFontSize": typo.get("title_font_size"),
        "titleYPercent": typo.get("title_y_percent"),
        "mainLine1Color": str(typo.get("main_line1_color") or "#FFFFFF"),
        "mainLine2Color": str(typo.get("main_line2_color") or "#FFFFFF"),
        "subtitleBarColor": str(typo.get("subtitle_bar_color") or "#FFEB3B"),
        "subtitleTextColor": str(typo.get("subtitle_text_color") or "#000000"),
        "coverImagePath": _rel_asset_path(cover_image_path, article_id=article_id, index=200)
        if cover_image_path
        else "",
        "coverIntroDurationSec": intro_sec,
    }


def _resolve_source_file(path: str) -> Path | None:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return None
    rooted = (Config.ROOT_DIR / raw.lstrip("/")).resolve()
    if rooted.is_file():
        return rooted
    candidate = Path(raw.lstrip("/"))
    if candidate.is_file():
        return candidate.resolve()
    return None


def _stage_asset(path: str, article_id: str, index: int) -> str:
    """Map an on-disk asset to a Remotion public/ path."""
    source = _resolve_source_file(path)
    if source is None:
        return str(path or "").lstrip("/")

    public_root = (remotion_project_dir() / "public").resolve()
    try:
        rel = source.relative_to(public_root)
        return rel.as_posix()
    except ValueError:
        pass

    try:
        rel_repo = source.relative_to(Config.ROOT_DIR.resolve())
        if rel_repo.as_posix().startswith("static/"):
            return rel_repo.as_posix()
    except ValueError:
        pass

    staged_dir = runtime_public_dir() / article_id
    staged_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix or ".bin"
    staged = staged_dir / f"asset_{index:02d}{suffix}"
    if not staged.exists() or staged.stat().st_mtime < source.stat().st_mtime:
        staged.write_bytes(source.read_bytes())
    return staged.relative_to(public_root).as_posix()


def _rel_asset_path(path: str, article_id: str = "shared", index: int = 0) -> str:
    return _stage_asset(path, article_id=article_id, index=index)


def render_with_remotion(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    bgm_path: str,
    background_image: str = "static/imgs/bg.png",
    durations: list[float] | None = None,
    template: dict[str, Any] | None = None,
    cover_image_path: str | None = None,
) -> dict[str, Any]:
    """Render ingested article video via Remotion CLI."""
    if not remotion_available():
        return {"success": False, "error": "remotion_not_installed"}

    if len(image_paths) < 1:
        return {"success": False, "error": "insufficient_images", "count": len(image_paths)}

    spec = template or {}
    layout_kind = str(spec.get("layout_kind") or "classic_overlay")
    composition = _composition_for_layout(layout_kind)
    clip_durations = durations or [2.5] * len(image_paths)

    cover_path = cover_image_path or ""
    if not cover_path and layout_kind == "chronicle_frame":
        cover_path = _maybe_render_cover(
            article_id=article_id,
            draft=draft,
            image_paths=image_paths,
            template=spec,
        )

    if layout_kind == "chronicle_frame":
        props = _build_chronicle_props(
            article_id=article_id,
            draft=draft,
            image_paths=image_paths,
            durations=clip_durations,
            bgm_path=bgm_path,
            template=spec,
            cover_image_path=cover_path,
        )
        suffix = "chronicle"
    else:
        props = _build_classic_props(
            article_id=article_id,
            draft=draft,
            image_paths=image_paths,
            durations=clip_durations,
            bgm_path=bgm_path,
            background_image=background_image,
            template=spec,
            cover_image_path=cover_path,
        )
        suffix = "classic"

    out_dir = Config.ROOT_DIR / "data" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{article_id}_{suffix}_remotion.mp4"
    props_path = out_dir / f"{article_id}_{suffix}_props.json"

    props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    env = os.environ.copy()
    env.setdefault(
        "REMOTION_CHROME_ARGS",
        "--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage",
    )
    node = _node_executable()

    cmd = [
        *resolve_npx_argv(),
        "remotion",
        "render",
        composition,
        str(out_path),
        f"--props={props_path}",
        "--codec=h264",
    ]
    if node:
        node_dir = str(Path(node).parent)
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
    logger.info(f"Remotion render start article={article_id} composition={composition}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(remotion_project_dir()),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "remotion_render_timeout"}
    except OSError as exc:
        return {"success": False, "error": f"remotion_spawn_failed: {exc}"}

    if proc.returncode != 0:
        logger.warning(f"Remotion render failed: {proc.stderr[-2000:]}")
        return {
            "success": False,
            "error": "remotion_render_failed",
            "stderr": proc.stderr[-4000:],
            "stdout": proc.stdout[-2000:],
        }

    if not out_path.is_file() or out_path.stat().st_size == 0:
        return {"success": False, "error": "remotion_output_missing"}

    intro_sec = float(props.get("coverIntroDurationSec") or 0)
    total_duration = intro_sec + sum(clip_durations[: len(image_paths)])
    rel = f"/{out_path.relative_to(Config.ROOT_DIR).as_posix()}"
    return {
        "success": True,
        "video_path": rel,
        "duration": float(total_duration),
        "renderer": "remotion",
        "composition": composition,
        "cover_image_path": cover_path or None,
        "cover_intro_sec": intro_sec,
    }
