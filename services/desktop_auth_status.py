"""Read desktop login status from the Rust auth session file for web UI fallbacks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.utils.paths import get_data_dir


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_future(value: str | None) -> bool:
    parsed = _parse_rfc3339(value)
    if parsed is None:
        return True
    now = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > now


def _session_path() -> Path:
    return get_data_dir() / "auth" / "session.json"


def get_desktop_auth_status() -> dict:
    base = {
        "authorized": False,
        "mode": None,
        "email": None,
        "phone": None,
        "accountStatus": None,
        "offlineExpiresAt": None,
        "message": None,
    }
    path = _session_path()
    if not path.is_file():
        return base
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base

    mode = data.get("mode")
    if mode == "offline":
        offline = data.get("offline") or {}
        expires_at = offline.get("expires_at")
        return {
            **base,
            "authorized": _is_future(expires_at),
            "mode": "offline",
            "email": offline.get("issued_to"),
            "offlineExpiresAt": expires_at,
        }

    if mode != "online":
        return base

    user = data.get("user") or {}
    account_status = user.get("account_status") or "inactive"
    email = user.get("email") or None
    if email == "":
        email = None
    phone = user.get("phone")
    has_token = bool(data.get("access_token") or data.get("access_token_sealed"))
    expires_at = data.get("expires_at")
    authorized = account_status == "active" and has_token and _is_future(expires_at)
    message = None
    if account_status != "active":
        message = "账号未激活或已停用"
    elif has_token and not _is_future(expires_at):
        message = "登录已过期，请在「账号」中重新登录"
    return {
        **base,
        "authorized": authorized,
        "mode": "online",
        "email": email,
        "phone": phone,
        "accountStatus": account_status,
        "message": message,
    }
