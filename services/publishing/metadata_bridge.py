"""Map AI summary draft fields to publish payload."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PublishDraftMetadata:
    main_line1: str = ""
    main_line2: str = ""
    sub_title: str = ""
    sub_title2: str = ""
    summary: str = ""
    praise_tags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    tags_text: str = ""


def normalize_wechat_title(main_line1: str, *, max_title_length: int = 30) -> str:
    """WeChat Channels title punctuation rules (other platforms unchanged)."""
    title = (main_line1 or "").strip()
    title = title.replace("！", "？").replace("-", "").replace(".", "点")
    if len(title) > max_title_length:
        title = title[:max_title_length]
    return title


def _format_hashtag_line(items: list[str]) -> str:
    tokens: list[str] = []
    for item in items:
        token = str(item).strip()
        if not token:
            continue
        if not token.startswith("#"):
            token = f"#{token}"
        tokens.append(token)
    return " ".join(tokens)


def _tags_description_line(draft: PublishDraftMetadata) -> str:
    if draft.tags_text.strip():
        return draft.tags_text.strip()
    tag_source = draft.praise_tags or draft.tags
    return _format_hashtag_line(tag_source)


def build_wechat_description(draft: PublishDraftMetadata) -> str:
    parts = [
        (draft.main_line2 or "").strip(),
        (draft.sub_title or "").strip(),
        (draft.sub_title2 or "").strip(),
        (draft.summary or "").strip(),
        _tags_description_line(draft),
    ]
    return "\n".join(part for part in parts if part)


def _parse_tag_list(draft: PublishDraftMetadata, *, max_tags: int) -> list[str]:
    if draft.tags:
        source = draft.tags
    elif draft.praise_tags:
        source = draft.praise_tags
    elif draft.tags_text.strip():
        raw = draft.tags_text.replace("#", " ")
        source = [t.strip() for t in raw.replace("，", ",").split(",") if t.strip()]
        if len(source) == 1 and " " in source[0]:
            source = source[0].split()
    else:
        source = []
    seen: set[str] = set()
    tags: list[str] = []
    for item in source:
        token = str(item).strip().lstrip("#")
        if not token or token in seen:
            continue
        seen.add(token)
        tags.append(token)
        if len(tags) >= max_tags:
            break
    return tags


def draft_from_video_draft(data: dict[str, Any]) -> PublishDraftMetadata:
    tags_raw = data.get("tags") or ""
    praise_tags = data.get("praise_tags") or []
    if not isinstance(praise_tags, list):
        praise_tags = []
    tags_text = tags_raw.strip() if isinstance(tags_raw, str) else ""
    tags_list: list[str] = []
    if isinstance(tags_raw, list):
        tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]
    return PublishDraftMetadata(
        main_line1=str(data.get("main_line1") or ""),
        main_line2=str(data.get("main_line2") or ""),
        sub_title=str(data.get("sub_title") or ""),
        sub_title2=str(data.get("sub_title2") or ""),
        summary=str(data.get("summary") or ""),
        praise_tags=praise_tags,
        tags=tags_list,
        tags_text=tags_text,
    )


def draft_to_publish_fields(
    draft: PublishDraftMetadata,
    *,
    max_title_length: int = 30,
    max_tags: int = 10,
    platform_id: str | None = None,
) -> dict:
    raw_title = (draft.main_line1 or "").strip()
    if platform_id in (None, "wechat_channels"):
        title = normalize_wechat_title(raw_title, max_title_length=max_title_length)
    else:
        title = raw_title[:max_title_length] if len(raw_title) > max_title_length else raw_title
    description = build_wechat_description(draft)
    tags = _parse_tag_list(draft, max_tags=max_tags)
    return {"title": title, "description": description, "tags": tags}
