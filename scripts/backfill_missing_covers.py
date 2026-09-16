#!/usr/bin/env python3
"""Regenerate publish covers for articles that have video but no generated_cover_path."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from services.ingestion.cover_picker import pick_best_cover_image
from services.ingestion.cover_render_service import render_article_cover
from services.ingestion.media_pipeline_trigger import load_media_pipeline_config
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle


def _parse_video_draft(article: IngestedArticle) -> dict:
    if article.video_draft_json:
        try:
            data = json.loads(article.video_draft_json)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"main_line1": (article.title or "未命名").strip()}


def backfill_covers(*, dry_run: bool = False, limit: int | None = None) -> int:
    init_db()
    factory = get_session_factory()
    cfg = load_media_pipeline_config()
    updated = 0

    with factory() as session:
        query = (
            session.query(IngestedArticle)
            .filter(IngestedArticle.generated_video_path.isnot(None))
            .filter(IngestedArticle.generated_video_path != "")
            .filter(
                (IngestedArticle.generated_cover_path.is_(None))
                | (IngestedArticle.generated_cover_path == "")
            )
            .order_by(IngestedArticle.generated_video_at.desc().nullslast())
        )
        if limit:
            query = query.limit(limit)
        articles = query.all()

    logger.info("Found {} articles missing covers", len(articles))
    for article in articles:
        with factory() as session:
            row = session.get(IngestedArticle, article.id)
            if row is None:
                continue
            cover_source = pick_best_cover_image(session, row.id)
            if not cover_source:
                logger.warning("Skip {}: no cover candidate", row.title)
                continue
            draft = _parse_video_draft(row)
            if dry_run:
                logger.info(
                    "Would render cover for {} using {}",
                    row.title,
                    cover_source["local_path"],
                )
                updated += 1
                continue
            result = render_article_cover(
                article_id=row.id,
                draft=draft,
                image_path=cover_source["local_path"],
                background_image=str(cfg.get("background_image", "static/imgs/bg.png")),
                width=int(cfg.get("cover_width", 1080)),
                height=int(cfg.get("cover_height", 1920)),
            )
            if not result.get("success"):
                logger.error("Cover failed for {}: {}", row.title, result.get("error"))
                continue
            row.generated_cover_path = result.get("cover_path")
            session.commit()
            logger.info("Cover saved for {}: {}", row.title, row.generated_cover_path)
            updated += 1

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    count = backfill_covers(dry_run=args.dry_run, limit=args.limit)
    print(f"Done. processed={count}")


if __name__ == "__main__":
    main()
