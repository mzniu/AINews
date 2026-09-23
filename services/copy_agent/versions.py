"""List and load playbook versions for the pattern lab."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from services.copy_agent.card_schema import (
    card_from_json,
    card_preview_from_stored,
    validate_body_warnings,
    validate_stored_quality,
)
from services.copy_agent.settings_store import get_settings
from src.db.models.playbook import CopyAgentJob, PatternCard, PlaybookVersion


def _card_for_version(session: Session, version_id: str) -> PatternCard | None:
    jobs = (
        session.query(CopyAgentJob)
        .filter_by(kind="curate")
        .order_by(CopyAgentJob.created_at.desc())
        .all()
    )
    for job in jobs:
        try:
            payload = json.loads(job.result_json or "{}")
        except json.JSONDecodeError:
            continue
        if payload.get("playbook_version_id") != version_id:
            continue
        card = session.query(PatternCard).filter_by(source_job_id=job.id).first()
        if card is not None:
            return card
    return None


def _card_preview(card: PatternCard | None) -> dict:
    if card is None:
        return {}
    return card_preview_from_stored(
        card_json=card.card_json,
        verdict_kind=card.verdict_kind or "",
        verdict_function=card.verdict_function or "",
        forbidden_transfers_json=card.forbidden_transfers_json or "[]",
        evidence_excerpt=card.evidence_excerpt or "",
    )


def list_playbook_versions(session: Session) -> dict:
    settings = get_settings(session)
    current_id = settings.current_playbook_version_id
    rows = session.query(PlaybookVersion).order_by(PlaybookVersion.created_at.desc()).all()
    versions = []
    for row in rows:
        body = (row.body or "").strip()
        preview = body if len(body) <= 160 else body[:160] + "…"
        card = _card_for_version(session, row.id)
        card_preview = _card_preview(card)
        pattern_name = str(card_preview.get("pattern_name") or "").strip()
        motives = card_preview.get("motives") if isinstance(card_preview.get("motives"), dict) else {}
        hook = card_preview.get("hook") if isinstance(card_preview.get("hook"), dict) else {}
        versions.append(
            {
                "id": row.id,
                "status": row.status,
                "trap_passed": bool(row.trap_passed),
                "is_current": row.id == current_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "body_preview": preview,
                "pattern_name": pattern_name,
                "motives_primary": str(motives.get("primary") or ""),
                "motives_primary_label": str(motives.get("primary_label") or ""),
                "hook_archetype_label": str(hook.get("archetype_label") or hook.get("archetype") or ""),
                "card_preview": card_preview,
            }
        )
    return {
        "current_playbook_version_id": current_id,
        "versions": versions,
    }


def labels_for_playbook_versions(session: Session, version_ids: set[str]) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for version_id in version_ids:
        if not version_id:
            continue
        card = _card_for_version(session, version_id)
        preview = _card_preview(card)
        motives = preview.get("motives") if isinstance(preview.get("motives"), dict) else {}
        hook = preview.get("hook") if isinstance(preview.get("hook"), dict) else {}
        labels[version_id] = {
            "pattern_name": str(preview.get("pattern_name") or ""),
            "motives_primary": str(motives.get("primary") or ""),
            "motives_primary_label": str(motives.get("primary_label") or ""),
            "hook_archetype_label": str(hook.get("archetype_label") or hook.get("archetype") or ""),
            "verdict_function_label": str(preview.get("verdict_function_label") or ""),
        }
    return labels


def get_playbook_version(session: Session, version_id: str) -> dict | None:
    row = session.get(PlaybookVersion, version_id)
    if row is None:
        return None
    settings = get_settings(session)
    card = _card_for_version(session, row.id)
    card_dict = card_from_json(card.card_json if card else None)
    return {
        "id": row.id,
        "status": row.status,
        "trap_passed": bool(row.trap_passed),
        "is_current": row.id == settings.current_playbook_version_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "body": row.body or "",
        "diff_yaml": row.diff_json or "",
        "card_preview": _card_preview(card),
        "body_issues": validate_body_warnings(card_dict, row.body or ""),
        "quality_issues": validate_stored_quality(card_dict, row.body or ""),
    }
