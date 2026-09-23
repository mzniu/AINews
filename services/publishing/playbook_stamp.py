"""Stamp playbook attribution onto a publish job before it is stored."""
from __future__ import annotations

_TRACKED = {"playbook", "edited"}
_FALLBACK = {"fact_gate_fallback", "generation_fallback"}


def playbook_source_from_draft(data: dict | None) -> dict:
    data = data or {}
    return {
        "playbook_version_id": data.get("playbook_version_id"),
        "copy_draft_id": data.get("copy_draft_id"),
        "playbook_attribution": data.get("playbook_attribution"),
    }


def stamp_playbook(job, source: dict | None) -> None:
    source = source or {}
    if source.get("playbook_version_id") == "constitution":
        raise ValueError("constitution is not a playbook id")
    attr = source.get("playbook_attribution") or None
    version = source.get("playbook_version_id") or None
    draft = source.get("copy_draft_id") or None
    if attr is None and version is None and draft is None:
        return
    if attr in _TRACKED:
        if not version or not draft:
            raise ValueError("playbook attribution requires version and draft")
    elif attr in _FALLBACK:
        version = None
        draft = None
    else:
        raise ValueError(f"invalid playbook attribution: {attr}")
    job.playbook_attribution = attr
    job.playbook_version_id = version
    job.copy_draft_id = draft
