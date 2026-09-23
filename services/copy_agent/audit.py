"""Path audit and env allowlist for the dsh subprocess.

Path audit only decides whether a curate result may be stored.
It does not confine the process.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_WIN_ABS = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'`<>|*?\r\n]+")
_REL_PATH = re.compile(r"(?:(?:\.{1,2}|[\w.-]+)[\\/])+[\w.-]+")
_TOOL_EVENT_TYPES = frozenset({"tool/call", "tool/result"})

_ALLOWLIST = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
    "USERNAME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
)


def harness_env(base: dict[str, str], extra_required: dict[str, str] | None = None) -> dict[str, str]:
    extra = extra_required or {}
    allowed = set(_ALLOWLIST) | set(extra)
    env = {key: value for key, value in base.items() if key in allowed and value is not None}
    env.update({key: value for key, value in extra.items() if value is not None})
    return env


def audit_tool_paths(jsonl_text: str, allowed_roots: list[Path]) -> list[str]:
    roots = [path.resolve() for path in allowed_roots]
    escaped: list[str] = []
    for line in (jsonl_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("type") or "") not in _TOOL_EVENT_TYPES:
            continue
        found: list[str] = []
        _collect_paths(payload, found)
        for raw in found:
            outside = _outside(raw, roots)
            if outside is not None:
                escaped.append(outside)
    return escaped


def _collect_paths(value, found: list[str]) -> None:
    if isinstance(value, str):
        found.extend(_path_candidates(value))
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_paths(item, found)
        return
    if isinstance(value, list):
        for item in value:
            _collect_paths(item, found)


def _path_candidates(text: str) -> list[str]:
    found: list[str] = []
    for match in _WIN_ABS.findall(text):
        if not _is_prose_path(match):
            _add(found, match)
    for match in _REL_PATH.findall(text):
        if not _is_prose_path(match):
            _add(found, match)
    return found


def _is_prose_path(text: str) -> bool:
    """Skip YAML/markdown ellipsis and Windows normalizing `dir\\...` to `dir`."""
    trimmed = text.rstrip("\\/")
    if trimmed.endswith("..."):
        return True
    name = Path(trimmed).name
    return bool(name) and set(name) <= {"."}


def _add(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _outside(raw: str, roots: list[Path]) -> str | None:
    try:
        path = Path(raw)
    except (OSError, ValueError):
        return None
    if path.is_absolute():
        return _outside_absolute(raw, roots)
    if ".." not in path.parts:
        return None
    try:
        if any((root / path).resolve().is_relative_to(root) for root in roots):
            return None
    except (OSError, ValueError):
        return raw
    return raw


def _outside_absolute(raw: str, roots: list[Path]) -> str | None:
    if _is_prose_path(raw):
        return None
    path = Path(raw)
    try:
        if path.exists():
            resolved = path.resolve()
            if any(resolved.is_relative_to(root) for root in roots):
                return None
            return raw
    except (OSError, ValueError):
        return None
    text = raw.rstrip("\\/")
    while len(text) > 3:
        text = text[:-1].rstrip("\\/")
        candidate = Path(text)
        try:
            if not candidate.exists() or candidate.parent == candidate:
                continue
            if not candidate.name or set(candidate.name) <= {"."}:
                continue
            resolved = candidate.resolve()
        except (OSError, ValueError):
            continue
        if any(resolved.is_relative_to(root) for root in roots):
            return None
        return str(candidate)
    return None
