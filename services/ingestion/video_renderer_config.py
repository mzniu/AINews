"""Desktop video renderer preferences and Remotion runtime marker (spec v1.1)."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from src.utils.config import Config
from src.utils.paths import get_data_dir, is_packaged

CONFIG_PATH = Config.CONFIG_DIR / "desktop_runtime.local.yaml"
REMOTION_MARKER_NAME = "remotion_v1.json"

Preferred = Literal["auto", "remotion", "python"]
ActiveRenderer = Literal["remotion", "python"]


@dataclass(frozen=True)
class RenderChoice:
    action: Literal["remotion", "python", "fail"]
    error: str | None = None
    fallback_from: str | None = None


def default_preferred_renderer() -> Preferred:
    return "auto" if is_packaged() else "remotion"


def _default_config() -> dict[str, Any]:
    return {
        "video_renderer": {
            "preferred": default_preferred_renderer(),
            "allow_python_fallback": True,
        },
        "npm": {"registry": None},
    }


def load_desktop_runtime_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return _default_config()
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        return _default_config()
    merged = _default_config()
    vr = loaded.get("video_renderer") if isinstance(loaded.get("video_renderer"), dict) else {}
    merged["video_renderer"]["preferred"] = _normalize_preferred(
        vr.get("preferred"), default=merged["video_renderer"]["preferred"]
    )
    if "allow_python_fallback" in vr:
        merged["video_renderer"]["allow_python_fallback"] = bool(vr.get("allow_python_fallback"))
    npm = loaded.get("npm") if isinstance(loaded.get("npm"), dict) else {}
    if "registry" in npm:
        merged["npm"]["registry"] = npm.get("registry")
    return merged


def save_desktop_runtime_config(patch: dict[str, Any]) -> dict[str, Any]:
    cfg = load_desktop_runtime_config()
    if "preferred" in patch:
        cfg["video_renderer"]["preferred"] = _normalize_preferred(patch["preferred"])
    if "allow_python_fallback" in patch:
        cfg["video_renderer"]["allow_python_fallback"] = bool(patch["allow_python_fallback"])
    if "npm_registry" in patch:
        cfg.setdefault("npm", {})["registry"] = patch.get("npm_registry")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, allow_unicode=True, sort_keys=False)
    return cfg


def _normalize_preferred(value: Any, *, default: str = "auto") -> Preferred:
    choice = str(value or default).strip().lower()
    if choice in ("auto", "remotion", "python"):
        return choice  # type: ignore[return-value]
    return default  # type: ignore[return-value]


def env_renderer_override() -> str | None:
    raw = os.environ.get("VIDEO_RENDERER")
    if raw is None or not str(raw).strip():
        return None
    choice = str(raw).strip().lower()
    if choice in ("python", "moviepy"):
        return "python"
    if choice == "remotion":
        return "remotion"
    return None


def remotion_marker_path() -> Path:
    return get_data_dir() / "runtime" / REMOTION_MARKER_NAME


def load_remotion_marker() -> dict[str, Any] | None:
    path = remotion_marker_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_remotion_lock_path() -> Path:
    return Config.ROOT_DIR / "remotion" / "package-lock.json"


def check_upgrade_required(
    marker: dict[str, Any] | None,
    app_version: str,
    lock_path: Path,
) -> bool:
    if not marker:
        return False
    if str(marker.get("app_version") or "") != str(app_version or ""):
        return True
    if not lock_path.is_file():
        return False
    expected = str(marker.get("remotion_lock_sha256") or "")
    if not expected:
        return False
    return sha256_file(lock_path) != expected


def remotion_runtime_ready(
    *,
    remotion_available: bool,
    marker: dict[str, Any] | None = None,
    app_version: str | None = None,
) -> tuple[bool, str]:
    """Return (ready, reason_code)."""
    if not remotion_available:
        return False, "node_modules_missing"
    lock_path = bundle_remotion_lock_path()
    version = app_version
    if version is None:
        from src.app_version import get_app_version

        version = get_app_version()
    if check_upgrade_required(marker, version, lock_path):
        return False, "upgrade_required"
    return True, "ok"


def compute_active_renderer(
    *,
    preferred: Preferred,
    allow_python_fallback: bool,
    remotion_ready: bool,
    env_override: str | None,
) -> tuple[ActiveRenderer, str | None]:
    if env_override == "python":
        return "python", "env_override"
    if env_override == "remotion":
        return "remotion", "env_override"
    if preferred == "python":
        return "python", None
    if preferred == "auto":
        return ("remotion", None) if remotion_ready else ("python", "remotion_not_ready")
    if remotion_ready:
        return "remotion", None
    if allow_python_fallback:
        return "python", "remotion_not_ready"
    return "python", "remotion_not_ready_blocked"


def choose_renderer_for_render(
    *,
    preferred: Preferred,
    allow_python_fallback: bool,
    remotion_ready: bool,
    env_override: str | None,
    call_override: str | None,
) -> RenderChoice:
    forced = call_override or env_override
    if forced == "python":
        return RenderChoice(action="python")
    if forced == "remotion":
        if not remotion_ready:
            if allow_python_fallback:
                return RenderChoice(action="python", fallback_from="remotion", error="remotion_not_ready")
            return RenderChoice(action="fail", error="remotion_not_ready")
        return RenderChoice(action="remotion")

    if preferred == "python":
        return RenderChoice(action="python")

    if preferred == "auto":
        if remotion_ready:
            return RenderChoice(action="remotion")
        return RenderChoice(action="python", fallback_from="remotion", error="remotion_not_ready")

    if remotion_ready:
        return RenderChoice(action="remotion")
    if allow_python_fallback:
        return RenderChoice(action="python", fallback_from="remotion", error="remotion_not_ready")
    return RenderChoice(action="fail", error="remotion_not_ready")


def build_video_renderer_status(
    *,
    remotion_available_fn,
    last_render_renderer: str | None = None,
) -> dict[str, Any]:
    cfg = load_desktop_runtime_config()
    vr = cfg.get("video_renderer") or {}
    preferred = _normalize_preferred(vr.get("preferred"))
    allow_fallback = bool(vr.get("allow_python_fallback", True))
    env_override = env_renderer_override()
    marker = load_remotion_marker()
    raw_available = bool(remotion_available_fn())
    ready, reason = remotion_runtime_ready(remotion_available=raw_available, marker=marker)
    active, active_note = compute_active_renderer(
        preferred=preferred,
        allow_python_fallback=allow_fallback,
        remotion_ready=ready,
        env_override=env_override,
    )
    lock_path = bundle_remotion_lock_path()
    from src.app_version import get_app_version

    upgrade = check_upgrade_required(marker, get_app_version(), lock_path)
    consistent = True
    repair_hint = None
    if preferred == "remotion" and not ready and not allow_fallback:
        consistent = raw_available or marker is not None
    if upgrade:
        repair_hint = "upgrade_required"
        ready = False
        reason = "upgrade_required"
    elif not ready and preferred in ("remotion", "auto") and not raw_available and marker:
        repair_hint = "install_incomplete"

    return {
        "preferred": preferred,
        "allow_python_fallback": allow_fallback,
        "consistent": consistent,
        "repair_hint": repair_hint,
        "remotion": {
            "ready": ready,
            "reason": reason,
            "project_dir": str(
                os.environ.get("REMOTION_PROJECT_DIR") or (Config.ROOT_DIR / "remotion")
            ),
            "node_version": marker.get("node_version") if marker else None,
            "lock_sha256": sha256_file(lock_path) if lock_path.is_file() else None,
            "upgrade_required": upgrade,
        },
        "python": {
            "ready": True,
            "layouts": ["chronicle_frame", "classic_overlay"],
        },
        "active": active,
        "active_note": active_note,
        "env_override": env_override,
        "last_render_renderer": last_render_renderer,
    }
