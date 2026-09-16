"""Build and parse per-post context for comment hub feed matching."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from services.publishing.adapters.wechat_channels_audience_reply import (
    build_wechat_feed_match_spec,
    extract_wechat_copy_lines,
)
from src.db.models.ingestion import IngestedArticle
from src.db.models.publishing import PublishJob


def _draft_copy_from_job(session: Session, job: PublishJob | None) -> dict[str, str]:
    copy = {
        "main_line1": "",
        "main_line2": "",
        "sub_title": "",
        "sub_title2": "",
        "description": "",
    }
    if job is None:
        return copy
    copy["description"] = str(job.description or "")
    if not job.source_id:
        return _enrich_copy_from_description(copy)
    article = session.get(IngestedArticle, job.source_id)
    if not article or not article.video_draft_json:
        return _enrich_copy_from_description(copy)
    try:
        draft = json.loads(article.video_draft_json)
    except json.JSONDecodeError:
        return _enrich_copy_from_description(copy)
    if not isinstance(draft, dict):
        return _enrich_copy_from_description(copy)
    copy["main_line1"] = str(draft.get("main_line1") or "").strip()
    copy["main_line2"] = str(draft.get("main_line2") or "").strip()
    copy["sub_title"] = str(draft.get("sub_title") or "").strip()
    copy["sub_title2"] = str(draft.get("sub_title2") or "").strip()
    return _enrich_copy_from_description(copy)


def _enrich_copy_from_description(copy: dict[str, str]) -> dict[str, str]:
    merged = extract_wechat_copy_lines(
        copy.get("description"),
        main_line1=copy.get("main_line1"),
        main_line2=copy.get("main_line2"),
        sub_title=copy.get("sub_title"),
        sub_title2=copy.get("sub_title2"),
    )
    return {**copy, **merged}


def build_wechat_inbox_post_context(
    *,
    post_row: dict[str, Any],
    job: PublishJob | None,
    session: Session,
) -> dict[str, Any]:
    """Snapshot fields needed to re-select the same feed in comment hub."""
    copy = _draft_copy_from_job(session, job)
    spec = build_wechat_feed_match_spec(
        copy["description"] or (job.description if job else None),
        str(post_row.get("title") or (job.title if job else "") or ""),
        main_line1=copy["main_line1"],
        main_line2=copy["main_line2"],
        sub_title=copy["sub_title"],
        sub_title2=copy["sub_title2"],
    )
    hub_feed_text = str(post_row.get("hub_feed_text") or "").strip()
    required = list(spec["required"])
    preferred = list(spec["preferred"])
    if hub_feed_text:
        # Sidebar text captured at scan time; reply uses prefix (startsWith) matching.
        required = [hub_feed_text[:160]]
    return {
        "export_id": str(post_row.get("export_id") or ""),
        "hub_feed_text": hub_feed_text,
        "feed_match_required": [item for item in dict.fromkeys(required) if item],
        "feed_match_preferred": [item for item in dict.fromkeys(preferred) if item],
        "main_line1": copy["main_line1"],
        "main_line2": copy["main_line2"],
        "sub_title": copy["sub_title"],
        "sub_title2": copy["sub_title2"],
        "description": copy["description"],
    }


def parse_post_context(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _is_stale_main_line1_required(ctx: dict[str, Any], required: list[str]) -> bool:
    if len(required) != 1:
        return False
    needle = required[0]
    main_line1 = str(ctx.get("main_line1") or "").strip()
    return bool(main_line1 and needle == main_line1)


def _rebuild_match_spec_from_context(ctx: dict[str, Any]) -> dict[str, list[str]]:
    return build_wechat_feed_match_spec(
        ctx.get("description"),
        None,
        main_line1=ctx.get("main_line1"),
        main_line2=ctx.get("main_line2"),
        sub_title=ctx.get("sub_title"),
        sub_title2=ctx.get("sub_title2"),
    )


def match_spec_from_post_context(ctx: dict[str, Any]) -> dict[str, list[str]] | None:
    required = [str(item).strip() for item in (ctx.get("feed_match_required") or []) if str(item).strip()]
    preferred = [str(item).strip() for item in (ctx.get("feed_match_preferred") or []) if str(item).strip()]
    hub = str(ctx.get("hub_feed_text") or "").strip()
    if hub:
        required = [hub[:160]]
    elif _is_stale_main_line1_required(ctx, required):
        rebuilt = _rebuild_match_spec_from_context(ctx)
        required = rebuilt["required"]
        preferred = rebuilt["preferred"] or preferred
    elif len(required) > 1:
        # Older snapshots required main_line1 + sub_title; sidebar only shows one line.
        rebuilt = build_wechat_feed_match_spec(
            ctx.get("description"),
            None,
            main_line1=ctx.get("main_line1"),
            main_line2=ctx.get("main_line2"),
            sub_title=ctx.get("sub_title"),
            sub_title2=ctx.get("sub_title2"),
        )
        required = rebuilt["required"]
        preferred = rebuilt["preferred"] or preferred
    if not required and not preferred:
        copy = extract_wechat_copy_lines(
            None,
            main_line1=ctx.get("main_line1"),
            main_line2=ctx.get("main_line2"),
            sub_title=ctx.get("sub_title"),
            sub_title2=ctx.get("sub_title2"),
        )
        spec = build_wechat_feed_match_spec(
            None,
            None,
            main_line1=copy["main_line1"],
            main_line2=copy["main_line2"],
            sub_title=copy["sub_title"],
            sub_title2=copy["sub_title2"],
        )
        required = spec["required"]
        preferred = spec["preferred"]
    if not required:
        return None
    return {
        "required": [item for item in dict.fromkeys(required) if len(item) >= 4],
        "preferred": [item for item in dict.fromkeys(preferred) if len(item) >= 4],
    }


def build_feed_match_spec_from_job(
    session: Session,
    job: PublishJob | None,
    *,
    post_title: str = "",
) -> dict[str, list[str]] | None:
    copy = _draft_copy_from_job(session, job)
    spec = build_wechat_feed_match_spec(
        copy["description"] or (job.description if job else None),
        post_title or (job.title if job else ""),
        main_line1=copy["main_line1"],
        main_line2=copy["main_line2"],
        sub_title=copy["sub_title"],
        sub_title2=copy["sub_title2"],
    )
    if not spec["required"]:
        return None
    return spec


def resolve_wechat_feed_match_spec(
    session: Session,
    job: PublishJob | None,
    inbox_row: Any,
    post_title: str,
) -> dict[str, list[str]] | None:
    ctx = parse_post_context(getattr(inbox_row, "post_context_json", None))
    copy = _draft_copy_from_job(session, job)
    enriched = {
        **ctx,
        "main_line1": copy["main_line1"] or ctx.get("main_line1"),
        "main_line2": copy["main_line2"] or ctx.get("main_line2"),
        "sub_title": copy["sub_title"] or ctx.get("sub_title"),
        "sub_title2": copy["sub_title2"] or ctx.get("sub_title2"),
        "description": copy["description"] or ctx.get("description"),
    }
    spec = match_spec_from_post_context(enriched)
    if spec:
        return spec
    return build_wechat_feed_match_spec(
        copy["description"] or (job.description if job else None),
        post_title,
        main_line1=copy["main_line1"],
        main_line2=copy["main_line2"],
        sub_title=copy["sub_title"],
        sub_title2=copy["sub_title2"],
    )


def dumps_post_context(ctx: dict[str, Any]) -> str:
    return json.dumps(ctx, ensure_ascii=False)
