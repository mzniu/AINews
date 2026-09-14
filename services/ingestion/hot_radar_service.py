"""Fetch and match external hot-list radar (TopHub multi-board)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests
from loguru import logger
from sqlalchemy.orm import Session

from services.ingestion.hot_radar_settings import (
    enabled_boards,
    load_hot_radar_config,
    resolve_tophub_access_key,
)
from services.ingestion.story_cluster import title_similarity
from services.ingestion.url_utils import canonicalize_url
from src.db.models.ingestion import HotRadarItem, HotRadarSnapshot, IngestedArticle, _uuid
from src.utils.config import Config

_HEAT_RE = re.compile(r"(\d+(?:\.\d+)?)(万|亿)?")
_TOPHUB_SOURCE = "tophub"


@dataclass(frozen=True)
class HotRadarMatch:
    rank: int
    heat_label: str | None
    heat_value: int | None
    hot_title: str
    hot_url: str
    match_method: str
    board: str
    source: str
    board_id: str = ""
    board_name: str = ""
    board_display: str = ""
    confidence: float = 1.0
    effective_rank: int = 0
    inherited_from_article_id: str | None = None


def parse_chinese_heat(label: str | None) -> int | None:
    if not label:
        return None
    text = str(label).strip().replace(",", "")
    match = _HEAT_RE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or ""
    if unit == "万":
        value *= 10_000
    elif unit == "亿":
        value *= 100_000_000
    return int(value)


def _extract_sina_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    hot_list = inner.get("hotList") or []
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(hot_list, start=1):
        base = raw.get("base") or {}
        info = raw.get("info") or {}
        core = base.get("base") or {}
        title = str(info.get("title") or base.get("dynamicName") or "").strip()
        url = str(core.get("url") or "").strip()
        heat_label = str(info.get("hotValue") or "").strip() or None
        if not heat_label:
            for dec in base.get("decoration") or []:
                if "HotSearchDecoration" in str(dec.get("@type", "")):
                    heat_label = str(dec.get("hotValue") or "").strip() or heat_label
        if not title:
            continue
        items.append(
            {
                "rank": index,
                "title": title,
                "url": url,
                "heat_label": heat_label,
                "heat_value": parse_chinese_heat(heat_label),
                "external_id": str(core.get("uniqueId") or "").strip() or None,
            }
        )
    return items


def _extract_tophub_items(payload: dict[str, Any], *, hashid: str) -> list[dict[str, Any]]:
    if payload.get("error"):
        raise RuntimeError(str(payload.get("error")))
    data = payload.get("data") or {}
    raw_items = data.get("items") or []
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        rank = int(raw.get("rank") or index)
        extra = str(raw.get("extra") or "").strip() or None
        items.append(
            {
                "rank": rank,
                "title": title,
                "url": str(raw.get("url") or "").strip(),
                "heat_label": extra,
                "heat_value": parse_chinese_heat(extra),
                "external_id": hashid,
            }
        )
    return items


def fetch_tophub_board_items(*, hashid: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = config or load_hot_radar_config()
    access_key = resolve_tophub_access_key(cfg)
    if not access_key:
        raise RuntimeError("TopHub API Key 未配置，请在系统配置或环境变量 TOPHUB_ACCESS_KEY 中设置")
    base_url = str(cfg.get("api_base_url") or "https://api.tophubdata.com").rstrip("/")
    response = requests.get(
        f"{base_url}/nodes/{hashid}",
        timeout=30,
        headers={"Authorization": access_key, "User-Agent": Config.USER_AGENT},
    )
    response.raise_for_status()
    return _extract_tophub_items(response.json(), hashid=hashid)


def get_latest_snapshot(db: Session, *, source: str, board: str) -> HotRadarSnapshot | None:
    return (
        db.query(HotRadarSnapshot)
        .filter_by(source=source, board=board)
        .order_by(HotRadarSnapshot.fetched_at.desc())
        .first()
    )


def _board_label(board: dict[str, Any]) -> str:
    name = str(board.get("name") or "").strip()
    display = str(board.get("display") or "").strip()
    if name and display:
        return f"{name}·{display}"
    return name or display or str(board.get("id") or board.get("hashid") or "热榜")


def _refresh_single_board(
    db: Session,
    *,
    board: dict[str, Any],
    force: bool,
    max_age: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    hashid = str(board.get("hashid") or "").strip()
    board_id = str(board.get("id") or hashid)
    latest = get_latest_snapshot(db, source=_TOPHUB_SOURCE, board=hashid)
    if latest and not force:
        age = datetime.utcnow() - latest.fetched_at.replace(tzinfo=None)
        if age <= timedelta(minutes=max_age):
            return {
                "board_id": board_id,
                "hashid": hashid,
                "status": "fresh",
                "snapshot_id": latest.id,
                "item_count": latest.item_count,
                "fetched_at": latest.fetched_at.isoformat(),
            }

    snapshot = HotRadarSnapshot(source=_TOPHUB_SOURCE, board=hashid, fetched_at=datetime.utcnow())
    db.add(snapshot)
    db.flush()
    try:
        items = fetch_tophub_board_items(hashid=hashid, config=config)
        for row in items:
            db.add(
                HotRadarItem(
                    snapshot_id=snapshot.id,
                    rank=int(row["rank"]),
                    title=str(row["title"]),
                    url=str(row.get("url") or ""),
                    heat_label=row.get("heat_label"),
                    heat_value=row.get("heat_value"),
                    external_id=row.get("external_id"),
                )
            )
        snapshot.item_count = len(items)
        db.commit()
        logger.info(f"Hot radar refreshed: tophub/{hashid} ({_board_label(board)}) items={len(items)}")
        return {
            "board_id": board_id,
            "hashid": hashid,
            "status": "refreshed",
            "snapshot_id": snapshot.id,
            "item_count": len(items),
            "fetched_at": snapshot.fetched_at.isoformat(),
        }
    except Exception as exc:
        snapshot.error_message = str(exc)
        snapshot.item_count = 0
        db.commit()
        logger.warning(f"Hot radar refresh failed for {hashid}: {exc}")
        return {
            "board_id": board_id,
            "hashid": hashid,
            "status": "failed",
            "error": str(exc),
            "snapshot_id": snapshot.id,
        }


def refresh_hot_radar(db: Session, *, force: bool = False, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_hot_radar_config()
    if not cfg.get("enabled", True):
        return {"status": "disabled"}

    boards = enabled_boards(cfg)
    if not boards:
        return {"status": "no_boards", "message": "未启用任何热榜节点"}

    max_age = int(cfg.get("max_age_minutes", 1440))
    board_results = [
        _refresh_single_board(db, board=board, force=force, max_age=max_age, config=cfg) for board in boards
    ]
    refreshed = sum(1 for row in board_results if row.get("status") == "refreshed")
    failed = sum(1 for row in board_results if row.get("status") == "failed")
    if refreshed:
        overall = "refreshed"
    elif failed == len(board_results):
        overall = "failed"
    else:
        overall = "fresh"

    total_items = sum(int(row.get("item_count") or 0) for row in board_results)
    pipeline_result: dict[str, Any] | None = None
    if refreshed or force:
        from services.ingestion.hot_radar_batch import run_post_refresh_pipeline

        pipeline_result = run_post_refresh_pipeline(db, config=cfg)

    return {
        "status": overall,
        "source": _TOPHUB_SOURCE,
        "board_count": len(boards),
        "refreshed_boards": refreshed,
        "failed_boards": failed,
        "item_count": total_items,
        "boards": board_results,
        "pipeline": pipeline_result,
    }


def ensure_fresh_hot_radar(db: Session, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    return refresh_hot_radar(db, force=False, config=config)


def _url_match(article_url: str, hot_url: str) -> bool:
    if not article_url or not hot_url:
        return False
    left = canonicalize_url(article_url)
    right = canonicalize_url(hot_url)
    if left == right:
        return True
    left_path = left.split("?", 1)[0]
    right_path = right.split("?", 1)[0]
    if left_path == right_path:
        return True
    left_tail = left_path.rsplit("/", 1)[-1]
    right_tail = right_path.rsplit("/", 1)[-1]
    return bool(left_tail and left_tail == right_tail)


def _make_match(
    item: HotRadarItem,
    *,
    method: str,
    board: dict[str, Any],
) -> HotRadarMatch:
    hashid = str(board.get("hashid") or "")
    return HotRadarMatch(
        rank=item.rank,
        heat_label=item.heat_label,
        heat_value=item.heat_value,
        hot_title=item.title,
        hot_url=item.url,
        match_method=method,
        board=hashid,
        source=_TOPHUB_SOURCE,
        board_id=str(board.get("id") or hashid),
        board_name=str(board.get("name") or ""),
        board_display=str(board.get("display") or ""),
    )


def match_article_hot_radar(
    db: Session,
    *,
    title: str,
    url: str | None = None,
    config: dict[str, Any] | None = None,
    article_id: str | None = None,
) -> HotRadarMatch | None:
    from services.ingestion.hot_radar_batch import (
        find_best_match_for_article,
        get_persisted_match,
        persisted_match_to_hot_radar_match,
    )

    cfg = config or load_hot_radar_config()
    if not cfg.get("enabled", True):
        return None

    if article_id:
        row = get_persisted_match(db, article_id)
        if row is not None:
            return persisted_match_to_hot_radar_match(row)

    if article_id:
        article = db.get(IngestedArticle, article_id)
        if article is not None:
            candidate = find_best_match_for_article(db, article, config=cfg)
            if candidate is not None:
                from services.ingestion.hot_radar_batch import match_candidate_to_hot_radar_match

                return match_candidate_to_hot_radar_match(candidate)

    threshold = float(cfg.get("title_match_threshold", 0.72))
    article_url = url or ""
    article_title = title or ""

    url_match: HotRadarMatch | None = None
    title_match: HotRadarMatch | None = None
    title_score = 0.0

    for board in enabled_boards(cfg):
        hashid = str(board.get("hashid") or "")
        snapshot = get_latest_snapshot(db, source=_TOPHUB_SOURCE, board=hashid)
        if snapshot is None or snapshot.item_count <= 0 or snapshot.error_message:
            continue
        items = (
            db.query(HotRadarItem)
            .filter_by(snapshot_id=snapshot.id)
            .order_by(HotRadarItem.rank.asc())
            .all()
        )
        for item in items:
            if _url_match(article_url, item.url):
                candidate = _make_match(item, method="url", board=board)
                if url_match is None or candidate.rank < url_match.rank:
                    url_match = candidate
        for item in items:
            score = title_similarity(article_title, item.title)
            if score >= threshold and (title_match is None or score > title_score or (score == title_score and item.rank < title_match.rank)):
                title_score = score
                title_match = _make_match(item, method="title", board=board)

    return url_match or title_match


def seed_hot_radar_snapshot(
    db: Session,
    *,
    items: list[dict[str, Any]],
    source: str = _TOPHUB_SOURCE,
    board: str = "test_board",
    fetched_at: datetime | None = None,
) -> HotRadarSnapshot:
    snapshot = HotRadarSnapshot(
        id=_uuid(),
        source=source,
        board=board,
        fetched_at=fetched_at or datetime.utcnow(),
        item_count=len(items),
    )
    db.add(snapshot)
    db.flush()
    for row in items:
        db.add(
            HotRadarItem(
                snapshot_id=snapshot.id,
                rank=int(row["rank"]),
                title=str(row["title"]),
                url=str(row.get("url") or ""),
                heat_label=row.get("heat_label"),
                heat_value=row.get("heat_value"),
                external_id=row.get("external_id"),
            )
        )
    db.commit()
    return snapshot


def hot_radar_match_to_dict(match: HotRadarMatch | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {
        "rank": match.rank,
        "heat_label": match.heat_label,
        "heat_value": match.heat_value,
        "hot_title": match.hot_title,
        "hot_url": match.hot_url,
        "match_method": match.match_method,
        "board": match.board,
        "source": match.source,
        "board_id": match.board_id,
        "board_name": match.board_name,
        "board_display": match.board_display,
        "board_label": _board_label(
            {
                "id": match.board_id,
                "hashid": match.board,
                "name": match.board_name,
                "display": match.board_display,
            }
        ),
        "confidence": match.confidence,
        "effective_rank": match.effective_rank or match.rank,
        "inherited_from_article_id": match.inherited_from_article_id,
    }


def _item_row_to_dict(row: HotRadarItem, *, board: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "rank": row.rank,
        "title": row.title,
        "url": row.url,
        "heat_label": row.heat_label,
        "heat_value": row.heat_value,
        "external_id": row.external_id,
    }
    if board:
        payload["board_id"] = board.get("id")
        payload["board_hashid"] = board.get("hashid")
        payload["board_label"] = _board_label(board)
    return payload


def _board_snapshot_view(db: Session, board: dict[str, Any]) -> dict[str, Any]:
    hashid = str(board.get("hashid") or "")
    snapshot = get_latest_snapshot(db, source=_TOPHUB_SOURCE, board=hashid)
    if snapshot is None:
        return {
            "board_id": board.get("id"),
            "hashid": hashid,
            "name": board.get("name"),
            "display": board.get("display"),
            "snapshot_id": None,
            "fetched_at": None,
            "item_count": 0,
            "error_message": None,
            "status": "empty",
            "items": [],
        }
    items = (
        db.query(HotRadarItem)
        .filter_by(snapshot_id=snapshot.id)
        .order_by(HotRadarItem.rank.asc())
        .all()
    )
    status = "failed" if snapshot.error_message else ("ready" if snapshot.item_count else "empty")
    return {
        "board_id": board.get("id"),
        "hashid": hashid,
        "name": board.get("name"),
        "display": board.get("display"),
        "snapshot_id": snapshot.id,
        "fetched_at": snapshot.fetched_at,
        "item_count": snapshot.item_count,
        "error_message": snapshot.error_message,
        "status": status,
        "items": [_item_row_to_dict(row, board=board) for row in items],
    }


def get_hot_radar_snapshot_view(db: Session, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_hot_radar_config()
    boards_cfg = enabled_boards(cfg)
    board_views = [_board_snapshot_view(db, board) for board in boards_cfg]

    latest_fetched: datetime | None = None
    total_items = 0
    has_ready = False
    has_failed = False
    for view in board_views:
        total_items += int(view.get("item_count") or 0)
        fetched_at = view.get("fetched_at")
        if fetched_at and (latest_fetched is None or fetched_at > latest_fetched):
            latest_fetched = fetched_at
        status = view.get("status")
        if status == "ready":
            has_ready = True
        if status == "failed":
            has_failed = True

    if has_ready:
        overall_status = "ready"
    elif has_failed:
        overall_status = "failed"
    elif board_views:
        overall_status = "empty"
    else:
        overall_status = "disabled" if not cfg.get("enabled", True) else "empty"

    flat_items: list[dict[str, Any]] = []
    for view in board_views:
        flat_items.extend(view.get("items") or [])

    public_cfg = {
        "enabled": bool(cfg.get("enabled", True)),
        "provider": str(cfg.get("provider") or "tophub"),
        "source": _TOPHUB_SOURCE,
        "refresh_cron": cfg.get("refresh_cron"),
        "max_age_minutes": cfg.get("max_age_minutes"),
        "title_match_threshold": cfg.get("title_match_threshold"),
        "api_base_url": cfg.get("api_base_url"),
        "board_count": len(boards_cfg),
        "has_access_key": bool(resolve_tophub_access_key(cfg)),
    }

    return {
        "snapshot_id": board_views[0].get("snapshot_id") if len(board_views) == 1 else None,
        "source": _TOPHUB_SOURCE,
        "board": "multi",
        "fetched_at": latest_fetched,
        "item_count": total_items,
        "error_message": next((v.get("error_message") for v in board_views if v.get("error_message")), None),
        "items": flat_items,
        "boards": board_views,
        "config": public_cfg,
        "status": overall_status,
    }


def get_article_hot_radar_view(
    db: Session,
    article: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_hot_radar_config()
    snapshot_view = get_hot_radar_snapshot_view(db, config=cfg)
    live_match = match_article_hot_radar(
        db,
        title=article.title or "",
        url=article.canonical_url,
        config=cfg,
        article_id=article.id,
    )

    stored_match: dict[str, Any] | None = None
    hot_radar_dimension: dict[str, Any] | None = None
    viral_score_total: float | None = None
    viral_score_grade: str | None = None
    publish_tier: str | None = None
    if article.score_breakdown_json:
        try:
            breakdown = json.loads(article.score_breakdown_json)
            stored_match = breakdown.get("hot_radar")
            final = breakdown.get("final") or {}
            viral = breakdown.get("viral") or {}
            viral_score_total = final.get("viral_total", viral.get("total"))
            viral_score_grade = final.get("viral_grade", viral.get("grade"))
            publish_tier = final.get("publish_tier")
            for dim in breakdown.get("dimensions") or []:
                if dim.get("key") == "hot_radar":
                    hot_radar_dimension = dim
                    break
        except json.JSONDecodeError:
            pass

    return {
        "article_id": article.id,
        "article_title": article.title,
        "article_url": article.canonical_url,
        "score_total": article.score_total,
        "score_grade": article.score_grade,
        "viral_score_total": viral_score_total,
        "viral_score_grade": viral_score_grade,
        "publish_tier": publish_tier,
        "scored_at": article.scored_at,
        "matched": live_match is not None,
        "match": hot_radar_match_to_dict(live_match),
        "stored_match": stored_match,
        "hot_radar_dimension": hot_radar_dimension,
        "snapshot": {
            "snapshot_id": snapshot_view.get("snapshot_id"),
            "fetched_at": snapshot_view.get("fetched_at"),
            "item_count": snapshot_view.get("item_count"),
            "status": snapshot_view.get("status"),
            "boards": snapshot_view.get("boards") or [],
        },
        "config": snapshot_view.get("config") or {},
    }


# Backward-compatible alias for Sina fixture tests
_extract_items = _extract_sina_items
