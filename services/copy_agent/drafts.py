"""One homepage draft from the current playbook. Tests inject complete()."""
from __future__ import annotations

import json
from collections.abc import Callable

from sqlalchemy.orm import Session

from services.content_generation_service import build_video_content_messages
from services.copy_agent.fact_gate import fact_gate
from services.copy_agent.pattern_ranking import (
    CompleteRank,
    PlaybookSelection,
    material_fingerprint,
    rank_playbook_for_material,
    ranking_adaptive_enabled,
    selection_to_json,
)
from services.copy_agent.settings_store import get_settings
from src.db.models.playbook import CopyDraft, PlaybookVersion

Complete = Callable[[list[dict]], str]


class NoPlaybook(RuntimeError):
    pass


class DraftNotSelectable(RuntimeError):
    pass


def _prose_for_gate(text: str) -> str:
    """Fact-gate the words, not the JSON field names."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(parsed, (dict, list)):
        return text
    parts: list[str] = []

    def walk(value) -> None:
        if isinstance(value, str):
            parts.append(value)
            return
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            parts.append(str(value))
            return
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(parsed)
    return "\n".join(parts)


def _ranked_top3(selection: PlaybookSelection) -> list[dict]:
    try:
        parsed = json.loads(selection.get("ranking_json") or "{}")
    except json.JSONDecodeError:
        return []
    ranked = parsed.get("ranked") if isinstance(parsed.get("ranked"), list) else []
    out: list[dict] = []
    for row in ranked[:3]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "cluster_key": row.get("cluster_key"),
                "score": row.get("score"),
            }
        )
    return out


def generate_one_draft(
    session: Session,
    *,
    title: str,
    content: str,
    complete: Complete,
    complete_rank: CompleteRank | None = None,
    force_current_playbook: bool = False,
    for_auto_pipeline: bool = False,
    article_id: str | None = None,
    voiceover_min_chars: int = 70,
    voiceover_max_chars: int = 90,
) -> CopyDraft:
    settings = get_settings(session)
    current_id = settings.current_playbook_version_id
    adaptive = (
        not force_current_playbook
        and ranking_adaptive_enabled(settings, for_auto_pipeline=for_auto_pipeline)
    )

    selection: PlaybookSelection | None = None
    version_id: str | None = None

    if adaptive and complete_rank is not None:
        try:
            selection = rank_playbook_for_material(
                session,
                title=title,
                content=content,
                complete_rank=complete_rank,
                adaptive=True,
                current_version_id=current_id,
                max_candidates=int(settings.ranking_max_candidates or 40),
                article_id=article_id,
                use_selection_cache=True,
            )
            version_id = selection.get("playbook_version_id")
        except Exception:
            if not current_id:
                raise
            selection = None
            version_id = current_id
    elif adaptive and complete_rank is None:
        adaptive = False

    if not version_id:
        version = None
        if current_id:
            version = session.get(PlaybookVersion, current_id)
        if version is None or not (version.body or "").strip():
            raise NoPlaybook("没有当前打法")
        version_id = version.id
        if selection is None:
            selection = {
                "playbook_version_id": version_id,
                "fallback": False,
                "confidence": "high",
                "reason": "",
                "policy_version": "rank-v1",
                "ranking_json": "{}",
            }

    version = session.get(PlaybookVersion, version_id)
    if version is None or not (version.body or "").strip():
        raise NoPlaybook("没有当前打法")

    messages = build_video_content_messages(
        title=title,
        content=content,
        voiceover_min_chars=voiceover_min_chars,
        voiceover_max_chars=voiceover_max_chars,
        playbook_body=version.body,
    )
    text = complete(messages)
    source = f"{title}\n{content}"
    gate = fact_gate(_prose_for_gate(text or ""), source)
    sel_json = (
        selection_to_json(
            selection,
            _ranked_top3(selection),
            material_fingerprint_value=material_fingerprint(title, content),
            article_id=article_id,
        )
        if selection
        else "{}"
    )
    draft = CopyDraft(
        playbook_version_id=version.id,
        body_json=json.dumps({"text": text or ""}, ensure_ascii=False),
        fact_gate_json=json.dumps(gate, ensure_ascii=False),
        selected=False,
        edited_after_select=False,
        selection_json=sel_json,
    )
    session.add(draft)
    session.commit()
    return draft


def draft_selectable(draft: CopyDraft) -> bool:
    try:
        gate = json.loads(draft.fact_gate_json or "{}")
    except json.JSONDecodeError:
        return False
    return bool(gate.get("passed"))


def select_draft(session: Session, draft_id: str, *, edited: bool = False) -> CopyDraft:
    draft = session.get(CopyDraft, draft_id)
    if draft is None:
        raise ValueError("稿不存在")
    if not draft_selectable(draft):
        raise DraftNotSelectable("这稿没过事实闸门，不能写入编辑框")
    draft.selected = True
    draft.edited_after_select = bool(edited)
    session.commit()
    return draft


def _selection_fields(draft: CopyDraft) -> dict:
    try:
        sel = json.loads(draft.selection_json or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(sel, dict):
        return {}
    out: dict = {}
    if sel.get("cluster_key"):
        out["pattern_cluster_key"] = sel["cluster_key"]
    if sel.get("pattern_name"):
        out["pattern_name"] = sel["pattern_name"]
    if sel.get("confidence"):
        out["playbook_selection_confidence"] = sel["confidence"]
    if sel.get("reason"):
        out["playbook_selection_reason"] = sel["reason"]
    if "fallback" in sel:
        out["playbook_selection_fallback"] = bool(sel.get("fallback"))
    return out


def draft_stamp_source(draft: CopyDraft) -> dict:
    if not draft.selected:
        return {}
    return {
        "playbook_attribution": "edited" if draft.edited_after_select else "playbook",
        "playbook_version_id": draft.playbook_version_id,
        "copy_draft_id": draft.id,
        **_selection_fields(draft),
    }
