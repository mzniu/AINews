"""Path whitelist helpers for publishing."""
from __future__ import annotations

from pathlib import Path

from src.utils.config import Config


class PathGuardError(ValueError):
    pass


def _root() -> Path:
    return Config.ROOT_DIR.resolve()


def resolve_video_path(raw: str) -> Path:
    cleaned = (raw or "").strip().lstrip("/").replace("\\", "/")
    if not cleaned:
        raise PathGuardError("video_path 不能为空")
    candidate = (_root() / cleaned).resolve()
    allowed = (_root() / "data" / "videos").resolve()
    if allowed not in candidate.parents:
        raise PathGuardError(f"video_path 不在允许目录: {raw}")
    if candidate.suffix.lower() != ".mp4":
        raise PathGuardError("video_path 必须是 .mp4")
    if not candidate.is_file():
        raise PathGuardError(f"视频文件不存在: {candidate}")
    return candidate


def resolve_cover_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    cleaned = raw.strip().lstrip("/").replace("\\", "/")
    candidate = (_root() / cleaned).resolve()
    allowed = (_root() / "data" / "publish" / "covers").resolve()
    allowed.mkdir(parents=True, exist_ok=True)
    if allowed not in candidate.parents:
        raise PathGuardError(f"cover_path 不在允许目录: {raw}")
    if not candidate.is_file():
        raise PathGuardError(f"封面文件不存在: {candidate}")
    return candidate


def to_relative_posix(path: Path) -> str:
    return path.resolve().relative_to(_root()).as_posix()
