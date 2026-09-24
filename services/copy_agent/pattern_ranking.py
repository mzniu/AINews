"""Rank pattern clusters for a material title + summary before draft generation."""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from services.copy_agent.card_schema import card_preview_from_stored, ranking_preview_from_card
from services.copy_agent.pattern_library import cluster_key_for, list_pattern_library
from src.db.models.playbook import CopyAgentSettings, CopyDraft, PatternCard, PlaybookVersion

CompleteRank = Callable[[list[dict]], str]

POLICY_VERSION = "rank-v1"
RANK_REASON_MAX_CHARS = 80


def clamp_rank_reason(text: object) -> str:
    reason = str(text or "").strip()
    if len(reason) <= RANK_REASON_MAX_CHARS:
        return reason
    return reason[: RANK_REASON_MAX_CHARS - 1] + "…"


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def repair_truncated_json_object(raw: str) -> str:
    s = _strip_json_fence(raw)
    if not s:
        return s
    start = s.find("{")
    if start > 0:
        s = s[start:]
    if s.count('"') % 2 == 1:
        s += '"'
    s = re.sub(r",\s*$", "", s)
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()
    while stack:
        s += stack.pop()
    return s


def _extract_ranking_from_fragment(text: str) -> dict | None:
    chosen = None
    m = re.search(r'"chosen_cluster_key"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text)
    if m:
        chosen = m.group(1).replace("\\\"", '"').strip()
    if not chosen:
        m2 = re.search(r'"cluster_key"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text)
        if m2:
            chosen = m2.group(1).replace("\\\"", '"').strip()
    if not chosen:
        return None
    conf = "low"
    mc = re.search(r'"confidence"\s*:\s*"([^"]+)"', text)
    if mc:
        conf = normalize_rank_confidence(mc.group(1))
    ranked: list[dict] = []
    block = re.search(r'"ranked"\s*:\s*\[', text)
    if block:
        tail = text[block.end() :]
        for row_m in re.finditer(
            r'\{\s*"cluster_key"\s*:\s*"([^"]+)"\s*,\s*"score"\s*:\s*([0-9.]+)\s*,\s*"reason"\s*:\s*"([^"]*)"',
            tail,
        ):
            ranked.append(
                {
                    "cluster_key": row_m.group(1),
                    "score": float(row_m.group(2)),
                    "reason": clamp_rank_reason(row_m.group(3)),
                }
            )
    if not ranked:
        ranked = [{"cluster_key": chosen, "score": 1.0, "reason": ""}]
    return {
        "chosen_cluster_key": chosen,
        "confidence": conf,
        "ranked": ranked,
    }


def parse_ranking_json_object(raw: str) -> dict:
    text = _strip_json_fence(raw)
    if not text:
        raise ValueError("ranking response empty")
    attempts = [text, repair_truncated_json_object(text)]
    for candidate in attempts:
        if not candidate:
            continue
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    extracted = _extract_ranking_from_fragment(text)
    if extracted is not None:
        return extracted
    raise ValueError("ranking response must be object")


def _no_playbook(message: str) -> None:
    from services.copy_agent.drafts import NoPlaybook

    raise NoPlaybook(message)


class TooManyPatterns(RuntimeError):
    pass


def normalize_rank_confidence(raw: object) -> str:
    text = str(raw or "").strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    aliases = {
        "h": "high",
        "高": "high",
        "较高": "high",
        "m": "medium",
        "mid": "medium",
        "中": "medium",
        "中等": "medium",
        "l": "low",
        "低": "low",
        "较低": "low",
    }
    if text in aliases:
        return aliases[text]
    for level in ("high", "medium", "low"):
        if level in text:
            return level
    return "low"


def _coerce_ranked_list(data: dict, *, chosen: str, allowed_keys: set[str]) -> list[dict]:
    ranked = data.get("ranked")
    if ranked is None:
        for alias in ("rankings", "ranking", "candidates_ranked", "ranked_patterns"):
            if data.get(alias) is not None:
                ranked = data.get(alias)
                break
    if isinstance(ranked, str):
        text = ranked.strip()
        if text.startswith("["):
            try:
                loaded = json.loads(text)
                ranked = loaded
            except json.JSONDecodeError:
                ranked = None
    if isinstance(ranked, dict):
        if ranked.get("cluster_key") or ranked.get("clusterKey"):
            ranked = [ranked]
        else:
            rows: list[dict] = []
            for key, val in ranked.items():
                cluster = str(key).strip()
                if not cluster:
                    continue
                if isinstance(val, dict):
                    row = dict(val)
                    row.setdefault("cluster_key", cluster)
                    rows.append(row)
                elif isinstance(val, (int, float)):
                    rows.append({"cluster_key": cluster, "score": float(val), "reason": ""})
                else:
                    rows.append(
                        {
                            "cluster_key": cluster,
                            "score": None,
                            "reason": clamp_rank_reason(val),
                        }
                    )
            ranked = rows
    if not isinstance(ranked, list):
        if chosen:
            return [{"cluster_key": chosen, "score": 1.0, "reason": ""}]
        return []
    rows: list[dict] = []
    for item in ranked:
        if isinstance(item, str):
            key = item.strip()
            if key in allowed_keys:
                rows.append({"cluster_key": key, "score": None, "reason": ""})
            continue
        if not isinstance(item, dict):
            continue
        row = dict(item)
        key = str(row.get("cluster_key") or row.get("clusterKey") or "").strip()
        if not key:
            continue
        row["cluster_key"] = key
        row.pop("clusterKey", None)
        rows.append(row)
    if not rows and chosen:
        rows = [{"cluster_key": chosen, "score": 1.0, "reason": ""}]
    return rows


class PlaybookSelection(TypedDict, total=False):
    playbook_version_id: str
    cluster_key: str | None
    pattern_name: str | None
    genre_label: str | None
    confidence: str
    reason: str
    fallback: bool
    recommended_version_id: str | None
    fallback_used_version_id: str | None
    policy_version: str
    ranking_json: str
    candidates_count: int
    prefiltered_from: int | None
    from_cache: bool


def validate_ranking_response(data: dict, allowed_keys: set[str]) -> dict:
    chosen = str(
        data.get("chosen_cluster_key")
        or data.get("cluster_key")
        or data.get("chosen")
        or ""
    ).strip()
    data["chosen_cluster_key"] = chosen
    if chosen not in allowed_keys:
        raise ValueError("chosen_cluster_key not in candidates")
    confidence = normalize_rank_confidence(data.get("confidence"))
    data["confidence"] = confidence
    ranked = _coerce_ranked_list(data, chosen=chosen, allowed_keys=allowed_keys)
    data["ranked"] = ranked
    if len(ranked) > len(allowed_keys):
        raise ValueError("ranked too long")
    for row in ranked:
        if not isinstance(row, dict):
            raise ValueError("ranked row must be object")
        key = str(row.get("cluster_key") or "").strip()
        if key and key not in allowed_keys:
            raise ValueError("ranked cluster_key not in candidates")
        score = row.get("score")
        if score is not None:
            try:
                s = float(score)
            except (TypeError, ValueError):
                raise ValueError("invalid score") from None
            if s < 0 or s > 1:
                raise ValueError("score out of range")
        reason = clamp_rank_reason(row.get("reason"))
        row["reason"] = reason
    rejected = data.get("rejected_cluster_keys")
    if rejected is not None:
        if not isinstance(rejected, list):
            raise ValueError("rejected_cluster_keys must be list")
        for key in rejected:
            if str(key).strip() not in allowed_keys:
                raise ValueError("rejected key not in candidates")
    return data


def choose_playbook_from_ranking(
    parsed: dict,
    candidates: list[dict],
    *,
    current_version_id: str | None,
) -> tuple[str | None, bool, str | None]:
    by_key = {c["cluster_key"]: c for c in candidates}
    chosen_key = str(parsed.get("chosen_cluster_key") or "").strip()
    chosen = by_key.get(chosen_key)
    recommended_id = (
        str(chosen.get("representative_version_id") or "") if chosen else None
    ) or None

    ranked = parsed.get("ranked") if isinstance(parsed.get("ranked"), list) else []
    scores: list[tuple[str, float]] = []
    for row in ranked:
        if not isinstance(row, dict):
            continue
        key = str(row.get("cluster_key") or "").strip()
        try:
            scores.append((key, float(row.get("score") or 0)))
        except (TypeError, ValueError):
            scores.append((key, 0.0))
    scores.sort(key=lambda item: item[1], reverse=True)

    confidence = str(parsed.get("confidence") or "").strip().lower()
    use_recommended = False
    if confidence == "high" and recommended_id:
        use_recommended = True
    elif confidence == "medium" and recommended_id:
        top = scores[0][1] if scores else 0.0
        second = scores[1][1] if len(scores) > 1 else 0.0
        if top - second >= 0.12:
            use_recommended = True

    if use_recommended and recommended_id:
        return recommended_id, False, recommended_id

    if current_version_id:
        return current_version_id, True, recommended_id

    return None, True, recommended_id


def resolve_representative_version_id(session: Session, version_ids: list[str]) -> str | None:
    ids = [vid for vid in version_ids if vid]
    if not ids:
        return None
    versions = [
        session.get(PlaybookVersion, vid)
        for vid in ids
    ]
    published = [
        v
        for v in versions
        if v is not None
        and (v.body or "").strip()
        and v.status == "published"
        and v.trap_passed
    ]
    if published:
        published.sort(key=lambda v: v.created_at or v.id, reverse=True)
        return published[0].id
    with_body = [v for v in versions if v is not None and (v.body or "").strip()]
    if not with_body:
        return None
    with_body.sort(key=lambda v: v.created_at or v.id, reverse=True)
    return with_body[0].id


def _latest_card_for_cluster(session: Session, genre: str, pattern_name: str) -> PatternCard | None:
    norm = re.sub(r"\s+", "", (pattern_name or "").strip().lower())
    cards = (
        session.query(PatternCard)
        .order_by(PatternCard.created_at.desc())
        .all()
    )
    from services.copy_agent.card_schema import card_from_json, is_v2_card

    for card in cards:
        card_dict = card_from_json(card.card_json)
        if not is_v2_card(card_dict):
            continue
        pattern = card_dict.get("pattern") if isinstance(card_dict.get("pattern"), dict) else {}
        g = str(pattern.get("genre") or "").strip() or "unknown"
        name = str(pattern.get("name") or "").strip() or "未命名模式"
        if g == genre and re.sub(r"\s+", "", name.lower()) == norm:
            return card
    return None


def build_ranking_candidates(session: Session) -> list[dict]:
    data = list_pattern_library(session)
    out: list[dict] = []
    for row in data.get("patterns") or []:
        if not isinstance(row, dict):
            continue
        genre = str(row.get("genre") or "").strip() or "unknown"
        name = str(row.get("pattern_name") or "").strip() or "未命名模式"
        version_ids = [str(v) for v in (row.get("version_ids") or []) if v]
        rep_id = resolve_representative_version_id(session, version_ids)
        if not rep_id:
            continue
        card = _latest_card_for_cluster(session, genre, name)
        preview = ranking_preview_from_card(
            card_preview_from_stored(
                card_json=card.card_json if card else None,
                verdict_kind=card.verdict_kind if card else "",
                verdict_function=card.verdict_function if card else "",
                forbidden_transfers_json=card.forbidden_transfers_json if card else "[]",
                evidence_excerpt=card.evidence_excerpt if card else "",
                include_evidence=False,
            )
        )
        key = cluster_key_for(genre, name)
        out.append(
            {
                "cluster_key": key,
                "genre": genre,
                "pattern_name": name,
                "genre_label": str(row.get("genre_label") or ""),
                "version_ids": version_ids,
                "representative_version_id": rep_id,
                **preview,
            }
        )
    return out


PREFILTER_TOP_K = 12


def material_fingerprint(title: str, content: str) -> str:
    text = f"{(title or '').strip()}\n{(content or '').strip()}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prefilter_candidates(
    candidates: list[dict],
    title: str,
    content: str,
    *,
    k: int = PREFILTER_TOP_K,
) -> list[dict]:
    if len(candidates) <= k:
        return candidates
    haystack = f"{title}\n{content}".lower()
    scored: list[tuple[int, dict]] = []
    for cand in candidates:
        score = 0
        for field in (
            cand.get("pattern_name"),
            cand.get("purpose"),
            cand.get("genre_label"),
            cand.get("verdict_function_label"),
        ):
            token = str(field or "").strip().lower()
            if len(token) >= 2 and token in haystack:
                score += 2
        for move_fn in cand.get("move_functions") or []:
            token = str(move_fn or "").strip().lower()
            if len(token) >= 2 and token in haystack:
                score += 1
        scored.append((score, cand))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("pattern_name") or "")))
    chosen = [cand for _, cand in scored[:k]]
    if len(chosen) < k:
        seen = {c["cluster_key"] for c in chosen}
        for cand in candidates:
            if cand["cluster_key"] in seen:
                continue
            chosen.append(cand)
            seen.add(cand["cluster_key"])
            if len(chosen) >= k:
                break
    return chosen


def lookup_cached_selection(
    session: Session,
    *,
    title: str,
    content: str,
    article_id: str | None,
    ttl_sec: int = 60,
) -> PlaybookSelection | None:
    fp = material_fingerprint(title, content)
    cutoff = datetime.utcnow() - timedelta(seconds=ttl_sec)
    drafts = (
        session.query(CopyDraft)
        .filter(CopyDraft.created_at >= cutoff)
        .order_by(CopyDraft.created_at.desc())
        .limit(30)
        .all()
    )
    for draft in drafts:
        try:
            sel = json.loads(draft.selection_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(sel, dict):
            continue
        if sel.get("material_fingerprint") != fp:
            continue
        stored_article = sel.get("article_id")
        if article_id and stored_article and stored_article != article_id:
            continue
        version_id = draft.playbook_version_id
        if not version_id:
            continue
        version = session.get(PlaybookVersion, version_id)
        if version is None or not (version.body or "").strip():
            continue
        return PlaybookSelection(
            playbook_version_id=version_id,
            cluster_key=sel.get("cluster_key"),
            pattern_name=sel.get("pattern_name"),
            genre_label=None,
            confidence=str(sel.get("confidence") or "high"),
            reason=str(sel.get("reason") or ""),
            fallback=bool(sel.get("fallback")),
            recommended_version_id=sel.get("recommended_version_id"),
            fallback_used_version_id=sel.get("fallback_used_version_id"),
            policy_version=str(sel.get("policy_version") or POLICY_VERSION),
            ranking_json=str(sel.get("ranking_json") or "{}"),
            candidates_count=int(sel.get("candidates_count") or 0),
            prefiltered_from=sel.get("prefiltered_from"),
            from_cache=True,
        )
    return None


def _parse_rank_json(raw: str) -> dict:
    return parse_ranking_json_object(raw)


def _ranking_messages(title: str, content: str, candidates: list[dict]) -> list[dict]:
    payload = {
        "material": {"title": title, "content": content},
        "candidates": [
            {
                "cluster_key": c["cluster_key"],
                "pattern_name": c.get("pattern_name"),
                "genre_label": c.get("genre_label"),
                "purpose": c.get("purpose"),
                "move_functions": c.get("move_functions"),
                "hook_archetype_label": c.get("hook_archetype_label"),
                "motives_primary_label": c.get("motives_primary_label"),
                "verdict_function_label": c.get("verdict_function_label"),
            }
            for c in candidates
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "你只根据候选模式列表为素材选一个最合适的 cluster_key。"
                "只输出 JSON，不要写稿。chosen_cluster_key 必须来自 candidates。"
                '格式：{"chosen_cluster_key":"...","confidence":"high|medium|low",'
                '"ranked":[{"cluster_key":"...","score":0.0,"reason":"..."}]}。'
                "ranked 必须是数组，至少包含 chosen 对应的一项；每条 reason 不超过 40 字。"
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def rank_playbook_for_material(
    session: Session,
    *,
    title: str,
    content: str,
    complete_rank: CompleteRank,
    adaptive: bool,
    current_version_id: str | None,
    max_candidates: int,
    article_id: str | None = None,
    use_selection_cache: bool = True,
) -> PlaybookSelection:
    max_material = int(os.getenv("PLAYBOOK_RANK_MAX_MATERIAL_CHARS", "1200"))
    material = (content or "")[:max_material]
    all_candidates = build_ranking_candidates(session)
    prefiltered_from: int | None = None

    if not adaptive:
        if not current_version_id:
            _no_playbook("没有当前打法")
        return _selection_for_version(
            session,
            current_version_id,
            fallback=False,
            reason="",
            confidence="high",
            ranking_json="{}",
            candidates_count=len(all_candidates),
            prefiltered_from=None,
            from_cache=False,
        )

    if not all_candidates:
        if not current_version_id:
            _no_playbook("没有当前打法")
        return _selection_for_version(
            session,
            current_version_id,
            fallback=False,
            reason="模式库为空，使用当前打法",
            confidence="high",
            ranking_json="{}",
            candidates_count=0,
            prefiltered_from=None,
            from_cache=False,
        )

    if use_selection_cache:
        cached = lookup_cached_selection(
            session, title=title, content=material, article_id=article_id
        )
        if cached is not None:
            return cached

    candidates = all_candidates
    if len(candidates) > max_candidates:
        prefiltered_from = len(candidates)
        candidates = prefilter_candidates(candidates, title, material, k=PREFILTER_TOP_K)

    messages = _ranking_messages(title, material, candidates)
    raw = complete_rank(messages)
    parsed = validate_ranking_response(
        _parse_rank_json(raw),
        {c["cluster_key"] for c in candidates},
    )
    version_id, fallback, recommended = choose_playbook_from_ranking(
        parsed,
        candidates,
        current_version_id=current_version_id,
    )
    if not version_id:
        _no_playbook("没有当前打法")

    chosen_key = str(parsed.get("chosen_cluster_key") or "").strip()
    chosen_row = next((c for c in candidates if c["cluster_key"] == chosen_key), {})
    reason = ""
    ranked = parsed.get("ranked") if isinstance(parsed.get("ranked"), list) else []
    for row in ranked:
        if isinstance(row, dict) and str(row.get("cluster_key")) == chosen_key:
            reason = str(row.get("reason") or "")
            break

    sel = _selection_for_version(
        session,
        version_id,
        fallback=fallback,
        reason=reason,
        confidence=str(parsed.get("confidence") or "low"),
        ranking_json=json.dumps(parsed, ensure_ascii=False),
        cluster_key=chosen_row.get("cluster_key") if not fallback else None,
        pattern_name=chosen_row.get("pattern_name") if not fallback else None,
        genre_label=chosen_row.get("genre_label") if not fallback else None,
        recommended_version_id=recommended if fallback else recommended,
        fallback_used_version_id=current_version_id if fallback else None,
        candidates_count=len(candidates),
        prefiltered_from=prefiltered_from,
        from_cache=False,
    )
    if fallback:
        sel["cluster_key"] = None
        sel["pattern_name"] = None
        sel["genre_label"] = None
    return sel


def _selection_for_version(
    session: Session,
    version_id: str,
    *,
    fallback: bool,
    reason: str,
    confidence: str,
    ranking_json: str,
    cluster_key: str | None = None,
    pattern_name: str | None = None,
    genre_label: str | None = None,
    recommended_version_id: str | None = None,
    fallback_used_version_id: str | None = None,
    candidates_count: int = 0,
    prefiltered_from: int | None = None,
    from_cache: bool = False,
) -> PlaybookSelection:
    version = session.get(PlaybookVersion, version_id)
    if version is None or not (version.body or "").strip():
        _no_playbook("没有当前打法")
    return PlaybookSelection(
        playbook_version_id=version_id,
        cluster_key=cluster_key,
        pattern_name=pattern_name,
        genre_label=genre_label,
        confidence=confidence,
        reason=reason,
        fallback=fallback,
        recommended_version_id=recommended_version_id,
        fallback_used_version_id=fallback_used_version_id,
        policy_version=POLICY_VERSION,
        ranking_json=ranking_json,
        candidates_count=candidates_count,
        prefiltered_from=prefiltered_from,
        from_cache=from_cache,
    )


def ranking_adaptive_enabled(settings: CopyAgentSettings, *, for_auto_pipeline: bool) -> bool:
    if for_auto_pipeline:
        return bool(
            settings.auto_uses_current_playbook and settings.auto_material_adaptive_playbook
        )
    return bool(settings.material_adaptive_playbook)


def production_rank_complete(messages: list[dict]) -> str:
    from services.content_generation_service import _build_openai_client
    from utils.content_compliance import _complete_json_text

    client, model, _base_url, profile = _build_openai_client()
    rank_model = os.getenv("PLAYBOOK_RANK_MODEL") or model
    create_kwargs: dict[str, Any] = {
        "model": rank_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": int(os.getenv("PLAYBOOK_RANK_MAX_TOKENS", "2048")),
        "response_format": {"type": "json_object"},
    }
    _response, result_text, _tokens = _complete_json_text(
        client=client,
        create_kwargs=create_kwargs,
        model=rank_model,
        kind="language",
        profile=profile,
        task="playbook_rank",
    )
    result = parse_ranking_json_object(result_text)
    return json.dumps(result, ensure_ascii=False)


def selection_to_json(
    selection: PlaybookSelection,
    ranked_top3: list[dict] | None = None,
    *,
    material_fingerprint_value: str | None = None,
    article_id: str | None = None,
) -> str:
    cluster = selection.get("cluster_key")
    genre = cluster.split("|", 1)[0] if cluster and "|" in cluster else None
    payload: dict[str, Any] = {
        "policy_version": selection.get("policy_version") or POLICY_VERSION,
        "cluster_key": cluster,
        "pattern_name": selection.get("pattern_name"),
        "genre": genre,
        "confidence": selection.get("confidence"),
        "reason": selection.get("reason"),
        "fallback": selection.get("fallback"),
        "recommended_version_id": selection.get("recommended_version_id"),
        "fallback_used_version_id": selection.get("fallback_used_version_id"),
        "ranked_top3": ranked_top3 or [],
        "candidates_count": selection.get("candidates_count"),
        "prefiltered_from": selection.get("prefiltered_from"),
        "from_cache": selection.get("from_cache"),
        "ranking_json": selection.get("ranking_json"),
    }
    if material_fingerprint_value:
        payload["material_fingerprint"] = material_fingerprint_value
    if article_id:
        payload["article_id"] = article_id
    return json.dumps(payload, ensure_ascii=False)


def selection_for_api(selection: PlaybookSelection) -> dict[str, Any]:
    return {
        "playbook_version_id": selection.get("playbook_version_id"),
        "cluster_key": selection.get("cluster_key"),
        "pattern_name": selection.get("pattern_name"),
        "genre_label": selection.get("genre_label"),
        "confidence": selection.get("confidence"),
        "reason": selection.get("reason"),
        "fallback": selection.get("fallback"),
        "recommended_version_id": selection.get("recommended_version_id"),
        "fallback_used_version_id": selection.get("fallback_used_version_id"),
        "policy_version": selection.get("policy_version"),
        "candidates_count": selection.get("candidates_count"),
        "prefiltered_from": selection.get("prefiltered_from"),
        "from_cache": selection.get("from_cache"),
    }


def ranked_rows_for_api(session: Session, selection: PlaybookSelection) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(selection.get("ranking_json") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    ranked = parsed.get("ranked") if isinstance(parsed.get("ranked"), list) else []
    if not ranked:
        return []
    by_key = {c["cluster_key"]: c for c in build_ranking_candidates(session)}
    chosen = str(parsed.get("chosen_cluster_key") or "").strip()
    out: list[dict[str, Any]] = []
    for row in ranked:
        if not isinstance(row, dict):
            continue
        key = str(row.get("cluster_key") or "").strip()
        meta = by_key.get(key, {})
        out.append(
            {
                "cluster_key": key,
                "pattern_name": meta.get("pattern_name") or "",
                "genre_label": meta.get("genre_label") or "",
                "score": row.get("score"),
                "reason": str(row.get("reason") or ""),
                "chosen": key == chosen,
            }
        )
    return out
