"""Enqueue ingestion for high-ranking hot radar URLs not yet in library."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from services.ingestion.hot_radar_matching import normalize_netloc
from services.ingestion.hot_radar_service import _TOPHUB_SOURCE, get_latest_snapshot
from services.ingestion.hot_radar_settings import enabled_boards, load_hot_radar_config
from services.ingestion.url_utils import canonicalize_url
from src.db.models.ingestion import HotRadarItem, IngestedArticle, IngestionJob


def _discovery_config(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("discovery") or {}


def _blocked_domains(cfg: dict[str, Any]) -> list[str]:
    return [str(d).strip().lower() for d in (_discovery_config(cfg).get("blocked_domains") or []) if d]


def is_url_blocked(url: str, *, config: dict[str, Any] | None = None) -> bool:
    cfg = config or load_hot_radar_config()
    host = normalize_netloc(urlparse(url).netloc)
    for domain in _blocked_domains(cfg):
        normalized = normalize_netloc(domain)
        if host == normalized or host.endswith(f".{normalized}"):
            return True
    return False


def resolve_source_for_url(url: str, *, config: dict[str, Any] | None = None) -> str | None:
    cfg = config or load_hot_radar_config()
    domain_map = _discovery_config(cfg).get("domain_source_map") or {}
    host = normalize_netloc(urlparse(url).netloc)
    for domain, source_id in domain_map.items():
        normalized = normalize_netloc(domain)
        if host == normalized or host.endswith(f".{normalized}"):
            return str(source_id)
    return None


def select_discovery_candidates(
    candidates: list[dict[str, Any]],
    *,
    per_board_max: int,
    max_urls_per_refresh: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    per_board: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(candidates, key=lambda item: (int(item.get("rank") or 9999), item.get("url") or "")):
        board_id = str(row.get("board_id") or "")
        bucket = per_board.setdefault(board_id, [])
        if len(bucket) >= max(0, per_board_max):
            continue
        bucket.append(row)

    merged = [row for rows in per_board.values() for row in rows]
    merged.sort(key=lambda item: (int(item.get("rank") or 9999), item.get("url") or ""))
    return merged[: max(0, max_urls_per_refresh)]


def _known_urls(db: Session) -> set[str]:
    return {row[0] for row in db.query(IngestedArticle.canonical_url).all()}


def _pending_discovery_urls(db: Session) -> set[str]:
    urls: set[str] = set()
    jobs = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.job_type == "hot_radar_discovery",
            IngestionJob.status.in_(("pending", "running")),
        )
        .all()
    )
    for job in jobs:
        try:
            payload = json.loads(job.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        url = payload.get("url")
        if url:
            urls.add(canonicalize_url(str(url)))
    return urls


def enqueue_hot_url_discoveries(db: Session, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_hot_radar_config()
    disc = _discovery_config(cfg)
    if not disc.get("enabled", False):
        return {"enqueued": 0, "skipped": 0, "candidates": 0}

    max_rank = int(disc.get("max_rank", 10))
    max_urls = int(disc.get("max_urls_per_refresh", 5))
    per_board_max = int(disc.get("per_board_max", max_urls))
    known = _known_urls(db)
    pending = _pending_discovery_urls(db)
    skipped = 0
    candidates: list[dict[str, Any]] = []

    for board in enabled_boards(cfg):
        board_id = str(board.get("id") or "")
        hashid = str(board.get("hashid") or "")
        snapshot = get_latest_snapshot(db, source=_TOPHUB_SOURCE, board=hashid)
        if snapshot is None or snapshot.error_message:
            continue
        items = (
            db.query(HotRadarItem)
            .filter_by(snapshot_id=snapshot.id)
            .order_by(HotRadarItem.rank.asc())
            .all()
        )
        for item in items:
            if item.rank > max_rank:
                continue
            url = canonicalize_url(item.url or "")
            if not url:
                skipped += 1
                continue
            if is_url_blocked(url, config=cfg):
                skipped += 1
                continue
            source_id = resolve_source_for_url(url, config=cfg)
            if not source_id:
                skipped += 1
                continue
            if url in known or url in pending:
                skipped += 1
                continue
            candidates.append(
                {
                    "rank": item.rank,
                    "url": url,
                    "source_id": source_id,
                    "title": item.title or "",
                    "board_id": board_id,
                    "board_hashid": hashid,
                    "snapshot_id": snapshot.id,
                    "heat_label": item.heat_label,
                }
            )

    selected = select_discovery_candidates(
        candidates,
        per_board_max=per_board_max,
        max_urls_per_refresh=max_urls,
    )
    enqueued = 0
    for row in selected:
        job = IngestionJob(job_type="hot_radar_discovery", source_id=row["source_id"], status="pending")
        job.payload_json = json.dumps(
            {
                "url": row["url"],
                "title": row["title"],
                "source_id": row["source_id"],
                "ingest_origin": "hot_radar_discovery",
                "board_id": row["board_id"],
                "board_hashid": row["board_hashid"],
                "snapshot_id": row["snapshot_id"],
                "rank": row["rank"],
                "heat_label": row.get("heat_label"),
            },
            ensure_ascii=False,
        )
        db.add(job)
        pending.add(row["url"])
        enqueued += 1
    db.commit()

    return {
        "enqueued": enqueued,
        "skipped": skipped,
        "candidates": len(candidates),
        "selected": len(selected),
    }


def _board_label_map(cfg: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for board in enabled_boards(cfg):
        board_id = str(board.get("id") or "")
        name = str(board.get("name") or "").strip()
        display = str(board.get("display") or "").strip()
        if name and display:
            labels[board_id] = f"{name}·{display}"
        else:
            labels[board_id] = name or display or board_id
    return labels


def _parse_job_payload(job: IngestionJob) -> dict[str, Any]:
    try:
        data = json.loads(job.payload_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _article_for_job(db: Session, job_id: str) -> IngestedArticle | None:
    from src.db.models.ingestion import CrawlRun

    run = (
        db.query(CrawlRun)
        .filter_by(job_id=job_id)
        .order_by(CrawlRun.started_at.desc())
        .first()
    )
    if run is None:
        return None
    return db.query(IngestedArticle).filter_by(crawl_run_id=run.id).first()


def _discovery_outcome(status: str, result: dict[str, Any]) -> str | None:
    if status == "failed":
        return "failed"
    if status != "succeeded":
        return None
    if result.get("failed"):
        return "failed"
    if result.get("skipped"):
        return "skipped"
    if result.get("new"):
        return "new"
    return None


def _resolve_article_for_job(
    db: Session,
    job: IngestionJob,
    payload: dict[str, Any],
) -> IngestedArticle | None:
    result = payload.get("result") or {}
    article_id = result.get("article_id")
    if article_id:
        article = db.get(IngestedArticle, article_id)
        if article is not None:
            return article

    article = _article_for_job(db, job.id)
    if article is not None:
        return article

    url = payload.get("url")
    source_id = payload.get("source_id") or job.source_id
    if url and source_id:
        return (
            db.query(IngestedArticle)
            .filter_by(source_id=source_id, canonical_url=canonicalize_url(url))
            .first()
        )
    return None


def get_hot_radar_discovery_queue_view(
    db: Session,
    *,
    limit: int = 50,
    hours: int = 72,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_hot_radar_config()
    board_labels = _board_label_map(cfg)
    since = datetime.utcnow() - timedelta(hours=max(1, int(hours)))
    jobs = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.job_type == "hot_radar_discovery",
            IngestionJob.created_at >= since,
        )
        .order_by(IngestionJob.created_at.desc())
        .limit(max(1, min(int(limit), 200)))
        .all()
    )

    summary = {"pending": 0, "running": 0, "succeeded": 0, "failed": 0}
    items: list[dict[str, Any]] = []
    for job in jobs:
        status = job.status or "pending"
        if status in summary:
            summary[status] += 1

        payload = _parse_job_payload(job)
        result = payload.get("result") or {}
        outcome = _discovery_outcome(status, result)
        article = (
            _resolve_article_for_job(db, job, payload)
            if status in {"succeeded", "running"}
            else None
        )

        url = payload.get("url") or (article.canonical_url if article else None)
        title = payload.get("title") or (article.title if article else None)
        board_id = payload.get("board_id")
        rank = payload.get("rank")
        try:
            rank = int(rank) if rank is not None else None
        except (TypeError, ValueError):
            rank = None

        items.append(
            {
                "job_id": job.id,
                "status": status,
                "outcome": outcome,
                "source_id": job.source_id,
                "url": url,
                "title": title,
                "board_id": board_id,
                "board_label": board_labels.get(str(board_id or ""), board_id),
                "rank": rank,
                "heat_label": payload.get("heat_label"),
                "article_id": article.id if article else None,
                "error_message": job.error_message,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
            }
        )

    return {
        "items": items,
        "summary": summary,
        "limit": limit,
        "hours": hours,
    }
