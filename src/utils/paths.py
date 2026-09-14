"""Runtime path resolution for dev, portable, and packaged desktop builds."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator


def _detect_resource_dir() -> Path:
    env = os.getenv("AINEWS_RESOURCE_DIR", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_resource_dir() -> Path:
    return _detect_resource_dir()


def is_packaged() -> bool:
    return bool(os.getenv("AINEWS_RESOURCE_DIR", "").strip()) or getattr(sys, "frozen", False)


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    env = os.getenv("AINEWS_DATA_DIR", "").strip()
    if env:
        return Path(env).resolve()
    return get_resource_dir() / "data"


def get_config_dir() -> Path:
    return get_data_dir() / "config"


def get_runtime_config_path(filename: str | Path) -> Path:
    """Resolve a writable runtime config file beneath the data directory."""
    return get_config_dir() / Path(filename)


def resolve_data_path(rel: str | Path) -> Path:
    """Resolve stored paths like ``data/videos/foo.mp4`` under the data dir."""
    path = Path(rel)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "data":
        return get_data_dir() / Path(*parts[1:])
    return get_data_dir() / path


def normalize_stored_path(path: str | Path | None) -> str:
    """Normalize filesystem or web paths to ``data/...`` form under DATA_DIR."""
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("/data/"):
        return raw[1:]
    if raw.startswith("data/"):
        return raw
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(get_data_dir().resolve()).as_posix()
            return f"data/{rel}"
        except ValueError:
            return raw.lstrip("/")
    return f"data/{raw.lstrip('/')}"


def to_data_url_path(path: str | Path | None) -> str:
    """Return a browser URL under the ``/data`` static mount."""
    rel = normalize_stored_path(path)
    return f"/{rel}" if rel else ""


def path_relative_to_data(path: Path) -> str:
    """Persist a filesystem path as ``data/...`` relative to DATA_DIR."""
    try:
        rel = path.resolve().relative_to(get_data_dir().resolve()).as_posix()
        return f"data/{rel}"
    except ValueError:
        return path.name


def resolve_local_asset_path(path: str | Path | None) -> Path | None:
    """Resolve ingested/media paths; falls back to resource root for static assets."""
    raw = str(path or "").strip()
    if not raw:
        return None
    normalized = normalize_stored_path(raw)
    if normalized.startswith("data/"):
        candidate = resolve_data_path(normalized)
        if candidate.is_file():
            return candidate
    cleaned = raw.lstrip("/").replace("\\", "/")
    for root in (get_resource_dir(), get_data_dir()):
        candidate = (root / cleaned).resolve()
        if candidate.is_file():
            return candidate
    direct = Path(raw)
    if direct.is_file():
        return direct.resolve()
    return None


@contextmanager
def use_writable_workdir(subdir: str = "cache") -> Iterator[Path]:
    """Temporarily chdir to a writable folder under DATA_DIR (for MoviePy/FFmpeg temps)."""
    work = get_data_dir() / subdir
    work.mkdir(parents=True, exist_ok=True)
    prev = os.getcwd()
    os.chdir(work)
    try:
        yield work
    finally:
        os.chdir(prev)


def load_runtime_dotenv() -> None:
    """Load secrets from the writable data dir, then bundled/repo .env."""
    from dotenv import load_dotenv

    load_dotenv(get_data_dir() / ".env")
    load_dotenv(get_resource_dir() / ".env")


def ensure_runtime_dirs() -> None:
    for d in (
        get_data_dir(),
        get_config_dir(),
        get_data_dir() / "logs",
        get_data_dir() / "cache",
        get_data_dir() / "videos",
        get_data_dir() / "publish" / "sessions",
        get_data_dir() / "publish" / "profiles",
        get_data_dir() / "publish" / "qr",
        get_data_dir() / "publish" / "covers",
        get_data_dir() / "digital_human" / "avatars",
        get_data_dir() / "digital_human" / "audio",
        get_data_dir() / "digital_human" / "outputs",
        get_data_dir() / "ingested",
        get_data_dir() / "pip_outputs",
    ):
        d.mkdir(parents=True, exist_ok=True)
