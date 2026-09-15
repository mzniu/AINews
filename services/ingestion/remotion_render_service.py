"""Remotion-based video renderer (parallel path to Python/MoviePy pipeline)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from src.utils.config import Config

REMOTION_DIR = Config.ROOT_DIR / "remotion"
NODE_MODULES = REMOTION_DIR / "node_modules"
RUNTIME_PUBLIC_DIR = REMOTION_DIR / "public" / "runtime"


def remotion_available() -> bool:
    """Return True when Remotion dependencies are installed."""
    return (REMOTION_DIR / "package.json").is_file() and NODE_MODULES.is_dir()


def _composition_for_layout(layout_kind: str) -> str:
    if layout_kind == "chronicle_frame":
        return "ChronicleVideo"
    return "ClassicOverlayVideo"


def _build_chronicle_props(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    durations: list[float],
    bgm_path: str,
    template: dict[str, Any],
) -> dict[str, Any]:
    images = []
    for index, path in enumerate(image_paths):
        duration = float(durations[index]) if index < len(durations) else 2.5
        rel_path = _rel_asset_path(path, article_id=article_id, index=index)
        images.append({"path": rel_path, "duration": duration})
    return {
        "articleId": article_id,
        "draft": draft,
        "images": images,
        "audioPath": _rel_asset_path(bgm_path, article_id=article_id, index=99) if bgm_path else "",
        "template": template,
        "seed": article_id,
    }


def _build_classic_props(
    *,
    draft: dict[str, Any],
    image_paths: list[str],
    durations: list[float],
    bgm_path: str,
    background_image: str,
    template: dict[str, Any] | None,
) -> dict[str, Any]:
    typo = (template or {}).get("typography") or {}
    video_cfg = (template or {}).get("video") or {}
    images = []
    for index, path in enumerate(image_paths):
        duration = float(durations[index]) if index < len(durations) else 2.5
        images.append(
            {"path": _rel_asset_path(path, article_id="classic", index=index), "duration": duration}
        )
    return {
        "summary": draft.get("summary") or "",
        "main_line1": draft.get("main_line1") or "",
        "main_line2": draft.get("main_line2") or "",
        "subtitle": draft.get("sub_title") or "",
        "subtitle2": draft.get("sub_title2") or "",
        "images": images,
        "audioPath": _rel_asset_path(bgm_path, article_id="classic", index=99) if bgm_path else "",
        "backgroundImagePath": _rel_asset_path(background_image, article_id="classic", index=100),
        "tags": draft.get("tags") or "",
        "summaryHighlightKeywords": draft.get("highlight_keywords") or [],
        "showSummary": bool(video_cfg.get("show_summary", True)),
        "titleFontSize": typo.get("title_font_size"),
        "titleYPercent": typo.get("title_y_percent"),
        "mainLine1Color": str(typo.get("main_line1_color") or "#FFFFFF"),
        "mainLine2Color": str(typo.get("main_line2_color") or "#FFFFFF"),
    }


def _resolve_source_file(path: str) -> Path | None:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return None
    candidate = Path(raw.lstrip("/"))
    if candidate.is_file():
        return candidate.resolve()
    rooted = (Config.ROOT_DIR / raw.lstrip("/")).resolve()
    if rooted.is_file():
        return rooted
    return None


def _stage_asset(path: str, article_id: str, index: int) -> str:
    """Map an on-disk asset to a Remotion public/ path."""
    source = _resolve_source_file(path)
    if source is None:
        return str(path or "").lstrip("/")

    public_root = (REMOTION_DIR / "public").resolve()
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

    staged_dir = RUNTIME_PUBLIC_DIR / article_id
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

    if layout_kind == "chronicle_frame":
        props = _build_chronicle_props(
            article_id=article_id,
            draft=draft,
            image_paths=image_paths,
            durations=clip_durations,
            bgm_path=bgm_path,
            template=spec,
        )
        suffix = "chronicle"
    else:
        props = _build_classic_props(
            draft=draft,
            image_paths=image_paths,
            durations=clip_durations,
            bgm_path=bgm_path,
            background_image=background_image,
            template=spec,
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

    cmd = [
        "npx",
        "remotion",
        "render",
        composition,
        str(out_path),
        f"--props={props_path}",
        "--codec=h264",
    ]
    logger.info(f"Remotion render start article={article_id} composition={composition}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REMOTION_DIR),
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

    total_duration = sum(clip_durations[: len(image_paths)])
    rel = f"/{out_path.relative_to(Config.ROOT_DIR).as_posix()}"
    return {
        "success": True,
        "video_path": rel,
        "duration": float(total_duration),
        "renderer": "remotion",
        "composition": composition,
    }
