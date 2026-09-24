"""Single source for /api/health version (desktop sets AINEWS_APP_VERSION)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.utils.config import Config

_FALLBACK = "1.0.15"


def get_app_version() -> str:
    env = (os.environ.get("AINEWS_APP_VERSION") or "").strip()
    if env:
        return env
    cfg_path = Config.CONFIG_DIR / "app_version.txt"
    if cfg_path.is_file():
        text = cfg_path.read_text(encoding="utf-8").strip()
        if text:
            return text.splitlines()[0].strip()
    tauri_conf = Config.ROOT_DIR / "desktop" / "src-tauri" / "tauri.conf.json"
    if tauri_conf.is_file():
        try:
            data = json.loads(tauri_conf.read_text(encoding="utf-8"))
            version = str(data.get("version") or "").strip()
            if version:
                return version
        except (json.JSONDecodeError, OSError):
            pass
    return _FALLBACK
