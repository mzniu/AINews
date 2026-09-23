"""Apply the current playbook draft to an ingested article's video_draft_json."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from services.copy_agent.drafts import (
    DraftNotSelectable,
    NoPlaybook,
    draft_selectable,
    draft_stamp_source,
    generate_one_draft,
    select_draft,
)
from services.copy_agent.pattern_ranking import CompleteRank
from src.db.models.ingestion import IngestedArticle

Complete = Callable[[list[dict]], str]


def _parse_generated_payload(body_json: str) -> dict:
    try:
        outer = json.loads(body_json or "{}")
    except json.JSONDecodeError:
        return {}
    text = outer.get("text") if isinstance(outer, dict) else ""
    if not isinstance(text, str) or not text.strip():
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"voiceover_script": text}
    except json.JSONDecodeError:
        return {"voiceover_script": text}


def apply_playbook_draft_to_article(
    session: Session,
    article: IngestedArticle,
    *,
    complete: Complete,
    complete_rank: CompleteRank | None = None,
) -> IngestedArticle:
    content = (article.content_text or article.summary or "").strip()
    if not content:
        raise ValueError("文章内容为空，无法按打法出稿")
    draft = generate_one_draft(
        session,
        title=article.title or "",
        content=content,
        complete=complete,
        complete_rank=complete_rank,
    )
    if not draft_selectable(draft):
        raise DraftNotSelectable("这稿没过事实闸门，不能写入出片文案")
    select_draft(session, draft.id, edited=False)
    payload = _parse_generated_payload(draft.body_json)
    stamp = draft_stamp_source(draft)
    payload.update(stamp)
    article.video_draft_json = json.dumps(payload, ensure_ascii=False)
    article.video_draft_generated_at = datetime.utcnow()
    session.commit()
    session.refresh(article)
    return article
