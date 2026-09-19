"""In-memory render-template YAML preview (does not write local.yaml)."""
from __future__ import annotations

import copy
import shutil
import time
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from services.ingestion.cover_render_service import render_article_cover
from services.ingestion.render_templates import _require_layout_kind
from services.ingestion.video_render_service import render_ingested_video
from src.utils.config import Config
from src.utils.paths import get_data_dir, resolve_local_asset_path

SAMPLE_DRAFT: dict[str, Any] = {
    "main_line1": "大模型又变贵了",
    "main_line2": "这次是推理成本",
    "sub_title": "接口涨价背后",
    "sub_title2": "你的账单先响",
    "summary": "样例摘要：只用于预览模板配色、字号与档案框，不会写入资讯库。",
    "highlight_keywords": ["大模型", "推理"],
    "tags": "快讯",
}

PREVIEW_ARTICLE_ID = "template-preview"
PREVIEW_VIDEO_SEC = 3.0


def parse_preview_yaml(yaml_text: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid_yaml: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid_yaml: mapping required")
    _require_layout_kind(parsed)
    return parsed


def _preview_dir() -> Path:
    path = get_data_dir() / "cache" / "template-preview"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sample_image(template: dict[str, Any]) -> str:
    candidates = [
        str(template.get("background_image") or "").strip(),
        "static/imgs/templates/chronicle_tech_blue/bg.png",
        "static/imgs/bg-2.png",
        "static/imgs/bg.png",
    ]
    for raw in candidates:
        if not raw:
            continue
        resolved = resolve_local_asset_path(raw)
        if resolved is not None and resolved.is_file():
            return str(resolved)
        direct = Config.ROOT_DIR / raw.replace("\\", "/")
        if direct.is_file():
            return str(direct)
    fallback = _preview_dir() / "sample.jpg"
    if not fallback.is_file():
        Image.new("RGB", (800, 1200), (30, 80, 120)).save(fallback, format="JPEG")
    return str(fallback)


def _copy_into_preview(source: str | None, filename: str) -> Path:
    dest = _preview_dir() / filename
    if not source:
        if dest.is_file():
            return dest
        raise ValueError("preview_output_missing")
    resolved = resolve_local_asset_path(source)
    src = resolved if resolved is not None else Path(str(source).replace("\\", "/"))
    if src.is_file():
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest
    if dest.is_file():
        return dest
    raise ValueError("preview_output_missing")


def _data_url(filename: str) -> str:
    stamp = int(time.time() * 1000)
    return f"/data/cache/template-preview/{filename}?t={stamp}"


def preview_cover_from_yaml(yaml_text: str) -> dict[str, Any]:
    template = parse_preview_yaml(yaml_text)
    image_path = _sample_image(template)
    result = render_article_cover(
        article_id=PREVIEW_ARTICLE_ID,
        draft=SAMPLE_DRAFT,
        image_path=image_path,
        background_image=str(template.get("background_image") or image_path),
        template=template,
    )
    if not result.get("success"):
        raise ValueError(str(result.get("error") or "preview_cover_failed"))
    _copy_into_preview(result.get("cover_path"), "cover.jpg")
    return {"success": True, "image_url": _data_url("cover.jpg")}


def preview_video_from_yaml(yaml_text: str) -> dict[str, Any]:
    template = parse_preview_yaml(yaml_text)
    spec = copy.deepcopy(template)
    video = dict(spec.get("video") or {})
    video["min_duration_sec"] = PREVIEW_VIDEO_SEC
    table = dict(video.get("clip_durations_by_count") or {})
    table[1] = [PREVIEW_VIDEO_SEC]
    table["1"] = [PREVIEW_VIDEO_SEC]
    video["clip_durations_by_count"] = table
    spec["video"] = video
    image_path = _sample_image(spec)
    bgm = str(video.get("bgm_path") or "static/music/background.mp3")
    result = render_ingested_video(
        article_id=PREVIEW_ARTICLE_ID,
        draft=SAMPLE_DRAFT,
        image_paths=[image_path],
        bgm_path=bgm,
        background_image=str(spec.get("background_image") or image_path),
        clip_duration_sec=PREVIEW_VIDEO_SEC,
        template=spec,
        renderer="python",
    )
    if not result.get("success"):
        raise ValueError(str(result.get("error") or "preview_video_failed"))
    _copy_into_preview(result.get("video_path") or result.get("output_path"), "clip.mp4")
    return {"success": True, "video_url": _data_url("clip.mp4")}
