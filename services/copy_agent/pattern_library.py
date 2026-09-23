"""Pattern library: cluster cards by genre + name, battle rollups."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from services.copy_agent.card_schema import GENRES, card_from_json, is_v2_card
from services.copy_agent.versions import labels_for_playbook_versions
from src.db.models.playbook import CopyAgentJob, PatternCard, PlaybookVersion


def _normalize_key(name: str) -> str:
    return re.sub(r"\s+", "", (name or "").strip().lower())


def cluster_key_for(genre: str, pattern_name: str) -> str:
    g = (genre or "").strip() or "unknown"
    return f"{g}|{_normalize_key(pattern_name)}"


def _version_id_for_card(session: Session, card: PatternCard) -> str | None:
    if not card.source_job_id:
        return None
    job = session.get(CopyAgentJob, card.source_job_id)
    if job is None:
        return None
    try:
        payload = json.loads(job.result_json or "{}")
    except json.JSONDecodeError:
        return None
    version_id = payload.get("playbook_version_id")
    return str(version_id) if version_id else None


def list_pattern_library(session: Session) -> dict[str, Any]:
    clusters: dict[tuple[str, str], dict[str, Any]] = {}
    cards = session.query(PatternCard).order_by(PatternCard.created_at.desc()).all()
    for card in cards:
        card_dict = card_from_json(card.card_json)
        if not is_v2_card(card_dict):
            continue
        pattern = card_dict.get("pattern") if isinstance(card_dict.get("pattern"), dict) else {}
        genre = str(pattern.get("genre") or "").strip() or "unknown"
        name = str(pattern.get("name") or "").strip() or "未命名模式"
        key = (genre, _normalize_key(name))
        version_id = _version_id_for_card(session, card)
        hook = card_dict.get("hook") if isinstance(card_dict.get("hook"), dict) else {}
        motives = card_dict.get("motives") if isinstance(card_dict.get("motives"), dict) else {}
        entry = clusters.get(key)
        if entry is None:
            entry = {
                "genre": genre,
                "genre_label": GENRES.get(genre, genre),
                "pattern_name": name,
                "version_ids": [],
                "count": 0,
                "motives_primary": str(motives.get("primary") or ""),
                "hook_archetype": str(hook.get("archetype") or ""),
            }
            clusters[key] = entry
        entry["count"] += 1
        if version_id and version_id not in entry["version_ids"]:
            entry["version_ids"].append(version_id)

    patterns = sorted(
        clusters.values(),
        key=lambda row: (-int(row["count"]), row["pattern_name"]),
    )
    _attach_selection_stats(session, patterns, days=7)
    return {"patterns": patterns, "total": len(patterns)}


def _attach_selection_stats(session: Session, patterns: list[dict[str, Any]], *, days: int) -> None:
    from src.db.models.playbook import CopyDraft

    cutoff = datetime.utcnow() - timedelta(days=days)
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"selection_count": 0, "draft_count": 0, "pass_count": 0}
    )
    for draft in session.query(CopyDraft).filter(CopyDraft.created_at >= cutoff).all():
        try:
            sel = json.loads(draft.selection_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(sel, dict):
            continue
        key = str(sel.get("cluster_key") or "").strip()
        if not key:
            continue
        bucket = buckets[key]
        bucket["selection_count"] += 1
        bucket["draft_count"] += 1
        try:
            gate = json.loads(draft.fact_gate_json or "{}")
            if gate.get("passed"):
                bucket["pass_count"] += 1
        except json.JSONDecodeError:
            pass
    for row in patterns:
        genre = str(row.get("genre") or "").strip() or "unknown"
        name = str(row.get("pattern_name") or "").strip() or "未命名模式"
        key = cluster_key_for(genre, name)
        stats = buckets.get(key, {"selection_count": 0, "draft_count": 0, "pass_count": 0})
        row["selection_count_7d"] = stats["selection_count"]
        dc = stats["draft_count"]
        row["selection_pass_rate_7d"] = (
            round(stats["pass_count"] / dc, 3) if dc else None
        )


def build_pattern_library_markdown(session: Session, *, limit: int = 24) -> str:
    data = list_pattern_library(session)
    lines = [
        "# 已有模式库（同 genre + 模式名合并）",
        "",
        "写 card.yaml 时参考同类模式，保持抽象命名；不要照抄下列实例。",
        "",
    ]
    patterns = data["patterns"][:limit]
    if not patterns:
        lines.append("（尚无 v2 模式卡，你是第一条。）")
        return "\n".join(lines) + "\n"
    for row in patterns:
        lines.append(
            f"- **{row['pattern_name']}**（{row['genre_label']}）"
            f" · 共 {row['count']} 版"
            f" · 动机 {row['motives_primary'] or '—'}"
            f" · 钩子 {row['hook_archetype'] or '—'}"
        )
    lines.append("")
    lines.append("完整列表见产品内「模式库」。")
    return "\n".join(lines) + "\n"


def pattern_rollups_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "pattern_name": "",
            "playbook_version_ids": set(),
            "share_count": 0,
            "job_count": 0,
            "platforms": set(),
        }
    )
    for row in rows:
        if row.get("attribution") != "playbook":
            continue
        name = (row.get("pattern_name") or "").strip() or "未命名模式"
        bucket = buckets[name]
        bucket["pattern_name"] = name
        bucket["job_count"] += 1
        vid = row.get("playbook_version_id")
        if vid:
            bucket["playbook_version_ids"].add(vid)
        share = row.get("share_count")
        if isinstance(share, int):
            bucket["share_count"] += share
        platform = row.get("platform")
        if platform:
            bucket["platforms"].add(platform)
    rollups: list[dict[str, Any]] = []
    for bucket in buckets.values():
        rollups.append(
            {
                "pattern_name": bucket["pattern_name"],
                "job_count": bucket["job_count"],
                "share_count": bucket["share_count"],
                "playbook_version_ids": sorted(bucket["playbook_version_ids"]),
                "platforms": sorted(bucket["platforms"]),
            }
        )
    rollups.sort(key=lambda item: (-item["share_count"], -item["job_count"], item["pattern_name"]))
    return rollups


def enrich_rows_with_pattern_labels(session: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    version_ids = {row.get("playbook_version_id") for row in rows if row.get("playbook_version_id")}
    labels = labels_for_playbook_versions(session, {str(v) for v in version_ids if v})
    enriched: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        meta = labels.get(copy.get("playbook_version_id") or "", {})
        copy.setdefault("pattern_name", meta.get("pattern_name") or "")
        copy.setdefault("motives_primary_label", meta.get("motives_primary_label") or "")
        copy.setdefault("verdict_function_label", meta.get("verdict_function_label") or "")
        enriched.append(copy)
    return enriched
