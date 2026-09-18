"""Batch hot radar matching, persistence, inheritance, and re-score hooks."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from services.ingestion.hot_radar_matching import (
    compute_effective_rank,
    compute_final_confidence,
    compute_time_factor,
    match_urls,
    score_title_pair_with_embedding,
)
from services.ingestion.hot_radar_service import HotRadarMatch, _TOPHUB_SOURCE, get_latest_snapshot
from services.ingestion.hot_radar_settings import enabled_boards, load_hot_radar_config
from services.ingestion.story_cluster import load_entity_names
from src.db.models.ingestion import HotRadarArticleMatch, HotRadarItem, IngestedArticle


@dataclass(frozen=True)
class MatchCandidate:
    rank: int
    effective_rank: int
    confidence: float
    heat_label: str | None
    heat_value: int | None
    hot_title: str
    hot_url: str
    match_method: str
    board: str
    board_id: str
    board_name: str
    board_display: str
    snapshot_id: str
    hot_item_id: str | None = None
    inherited_from_article_id: str | None = None


def _matching_config(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("matching") or {}


def _board_weight(board: dict[str, Any]) -> float:
    return float(board.get("weight", 1.0))


def evaluate_pair(
    article: IngestedArticle,
    item: HotRadarItem,
    *,
    board: dict[str, Any],
    snapshot_fetched_at: datetime,
    config: dict[str, Any],
) -> MatchCandidate | None:
    match_cfg = _matching_config(config)
    entity_names = load_entity_names()

    url_ok, url_method, url_conf = match_urls(article.canonical_url or "", item.url or "")
    if url_ok:
        base_conf = url_conf
        method = url_method
    else:
        title_conf, method = score_title_pair_with_embedding(
            article.title or "",
            item.title or "",
            entity_names=entity_names,
            config=match_cfg,
        )
        if not method:
            return None
        base_conf = title_conf

    time_factor = compute_time_factor(
        article_published_at=article.published_at,
        snapshot_fetched_at=snapshot_fetched_at,
        config=match_cfg,
    )
    confidence = compute_final_confidence(
        base_conf,
        board_weight=_board_weight(board),
        time_factor=time_factor,
    )
    min_conf = float(match_cfg.get("min_confidence", 0.6))
    if confidence < min_conf:
        return None

    effective_rank = compute_effective_rank(item.rank, confidence, config=match_cfg)
    hashid = str(board.get("hashid") or "")
    return MatchCandidate(
        rank=item.rank,
        effective_rank=effective_rank,
        confidence=confidence,
        heat_label=item.heat_label,
        heat_value=item.heat_value,
        hot_title=item.title,
        hot_url=item.url,
        match_method=method,
        board=hashid,
        board_id=str(board.get("id") or hashid),
        board_name=str(board.get("name") or ""),
        board_display=str(board.get("display") or ""),
        snapshot_id=item.snapshot_id,
        hot_item_id=item.id,
    )


def _pick_best(candidates: list[MatchCandidate]) -> MatchCandidate | None:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (-row.confidence, row.effective_rank, row.rank),
    )[0]


def find_best_match_for_article(
    db: Session,
    article: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
) -> MatchCandidate | None:
    cfg = config or load_hot_radar_config()
    candidates: list[MatchCandidate] = []
    for board in enabled_boards(cfg):
        hashid = str(board.get("hashid") or "")
        snapshot = get_latest_snapshot(db, source=_TOPHUB_SOURCE, board=hashid)
        if snapshot is None or snapshot.item_count <= 0 or snapshot.error_message:
            continue
        items = db.query(HotRadarItem).filter_by(snapshot_id=snapshot.id).all()
        for item in items:
            candidate = evaluate_pair(
                article,
                item,
                board=board,
                snapshot_fetched_at=snapshot.fetched_at,
                config=cfg,
            )
            if candidate is not None:
                candidates.append(candidate)
    return _pick_best(candidates)


def _recent_articles(db: Session, *, days: int) -> list[IngestedArticle]:
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    return (
        db.query(IngestedArticle)
        .filter(IngestedArticle.created_at >= cutoff)
        .order_by(IngestedArticle.created_at.desc())
        .all()
    )


def batch_match_hot_radar(db: Session, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_hot_radar_config()
    batch_cfg = cfg.get("batch") or {}
    days = int(batch_cfg.get("rescore_days", 7))
    articles = _recent_articles(db, days=days)
    matched = 0
    article_ids: list[str] = []

    for article in articles:
        best = find_best_match_for_article(db, article, config=cfg)
        if best is None:
            db.query(HotRadarArticleMatch).filter_by(article_id=article.id).delete()
            continue

        db.query(HotRadarArticleMatch).filter_by(article_id=article.id, board_hashid=best.board).delete()
        db.add(
            HotRadarArticleMatch(
                article_id=article.id,
                industry_id=article.industry_id,
                snapshot_id=best.snapshot_id,
                hot_item_id=best.hot_item_id,
                board_hashid=best.board,
                board_id=best.board_id,
                rank=best.rank,
                effective_rank=best.effective_rank,
                confidence=best.confidence,
                match_method=best.match_method,
                heat_label=best.heat_label,
                heat_value=best.heat_value,
                hot_title=best.hot_title,
                hot_url=best.hot_url,
                inherited_from_article_id=best.inherited_from_article_id,
                matched_at=datetime.utcnow(),
            )
        )
        matched += 1
        article_ids.append(article.id)

    db.commit()
    return {"matched_articles": matched, "scanned_articles": len(articles), "article_ids": article_ids}


def apply_story_inheritance(db: Session, *, config: dict[str, Any] | None = None) -> int:
    cfg = config or load_hot_radar_config()
    inherit_cfg = cfg.get("inheritance") or {}
    if not inherit_cfg.get("enabled", True):
        return 0

    factor = float(inherit_cfg.get("confidence_factor", 0.85))
    rank_penalty = int(inherit_cfg.get("rank_penalty", 3))
    min_conf = float(_matching_config(cfg).get("min_confidence", 0.6))
    inherited_count = 0

    matched_rows = {
        row.article_id: row
        for row in db.query(HotRadarArticleMatch).all()
        if row.match_method != "story_inherit"
    }
    if not matched_rows:
        return 0

    members = db.query(IngestedArticle).filter(IngestedArticle.story_id.isnot(None)).all()
    by_story: dict[str, list[IngestedArticle]] = defaultdict(list)
    for article in members:
        by_story[article.story_id].append(article)

    for _story_id, story_members in by_story.items():
        sources = [member for member in story_members if member.id in matched_rows]
        if not sources:
            continue
        source_article = max(sources, key=lambda row: matched_rows[row.id].confidence)
        source_row = matched_rows[source_article.id]

        for member in story_members:
            if member.id in matched_rows or db.query(HotRadarArticleMatch).filter_by(article_id=member.id).first():
                continue
            inherited_conf = source_row.confidence * factor
            if inherited_conf < min_conf:
                continue
            db.add(
                HotRadarArticleMatch(
                    article_id=member.id,
                    industry_id=member.industry_id,
                    snapshot_id=source_row.snapshot_id,
                    hot_item_id=source_row.hot_item_id,
                    board_hashid=source_row.board_hashid,
                    board_id=source_row.board_id,
                    rank=source_row.rank,
                    effective_rank=source_row.effective_rank + rank_penalty,
                    confidence=inherited_conf,
                    match_method="story_inherit",
                    heat_label=source_row.heat_label,
                    heat_value=source_row.heat_value,
                    hot_title=source_row.hot_title,
                    hot_url=source_row.hot_url,
                    inherited_from_article_id=source_article.id,
                    matched_at=datetime.utcnow(),
                )
            )
            inherited_count += 1

    db.commit()
    return inherited_count


def get_persisted_match(db: Session, article_id: str) -> HotRadarArticleMatch | None:
    rows = (
        db.query(HotRadarArticleMatch)
        .filter_by(article_id=article_id)
        .order_by(HotRadarArticleMatch.confidence.desc(), HotRadarArticleMatch.effective_rank.asc())
        .all()
    )
    return rows[0] if rows else None


def match_candidate_to_hot_radar_match(candidate: MatchCandidate | HotRadarArticleMatch) -> HotRadarMatch:
    if isinstance(candidate, HotRadarArticleMatch):
        return HotRadarMatch(
            rank=candidate.effective_rank or candidate.rank,
            heat_label=candidate.heat_label,
            heat_value=candidate.heat_value,
            hot_title=candidate.hot_title,
            hot_url=candidate.hot_url,
            match_method=candidate.match_method,
            board=candidate.board_hashid,
            source=_TOPHUB_SOURCE,
            board_id=candidate.board_id,
            board_name="",
            board_display="",
            confidence=candidate.confidence,
            effective_rank=candidate.effective_rank or candidate.rank,
            inherited_from_article_id=candidate.inherited_from_article_id,
        )
    return HotRadarMatch(
        rank=candidate.effective_rank,
        heat_label=candidate.heat_label,
        heat_value=candidate.heat_value,
        hot_title=candidate.hot_title,
        hot_url=candidate.hot_url,
        match_method=candidate.match_method,
        board=candidate.board,
        source=_TOPHUB_SOURCE,
        board_id=candidate.board_id,
        board_name=candidate.board_name,
        board_display=candidate.board_display,
        confidence=candidate.confidence,
        effective_rank=candidate.effective_rank,
        inherited_from_article_id=candidate.inherited_from_article_id,
    )


def persisted_match_to_hot_radar_match(row: HotRadarArticleMatch) -> HotRadarMatch:
    return match_candidate_to_hot_radar_match(row)


def rescore_articles_with_hot_radar(db: Session, article_ids: list[str]) -> int:
    if not article_ids:
        return 0
    from services.ingestion.score_service import apply_score_to_article

    updated = 0
    for article_id in article_ids:
        article = db.get(IngestedArticle, article_id)
        if article is None:
            continue
        try:
            apply_score_to_article(db, article, use_llm=False)
            updated += 1
        except Exception as exc:
            logger.warning(f"Hot radar rescore failed for {article_id}: {exc}")
    return updated


def run_post_refresh_pipeline(db: Session, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_hot_radar_config()
    batch_result = batch_match_hot_radar(db, config=cfg)
    inherited = apply_story_inheritance(db, config=cfg)

    from services.ingestion.hot_radar_discovery import enqueue_hot_url_discoveries

    discovery_result = enqueue_hot_url_discoveries(db, config=cfg)

    rescored = 0
    batch_cfg = cfg.get("batch") or {}
    if batch_cfg.get("rescore_on_refresh", True):
        article_ids = list(batch_result.get("article_ids") or [])
        rescored = rescore_articles_with_hot_radar(db, article_ids)

    return {
        "batch": batch_result,
        "inherited": inherited,
        "discovery": discovery_result,
        "rescored": rescored,
    }
