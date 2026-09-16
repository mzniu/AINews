#!/usr/bin/env python3
"""Backfill Story.primary_article_id and StoryArticle roles from scores."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from services.ingestion.story_primary import refresh_story_primary
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import Story


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not commit changes")
    args = parser.parse_args()

    init_db()
    session = get_session_factory()()
    updated = 0
    try:
        stories = session.query(Story).order_by(Story.updated_at.desc()).all()
        for story in stories:
            before = story.primary_article_id
            primary_id = refresh_story_primary(session, story.id)
            if primary_id and primary_id != before:
                updated += 1
                logger.info(
                    "story={} primary {} -> {}",
                    story.id,
                    before,
                    primary_id,
                )
        if args.dry_run:
            session.rollback()
            logger.info("dry-run: would update %s stories", updated)
        else:
            session.commit()
            logger.info("updated {} stories", updated)
    finally:
        session.close()


if __name__ == "__main__":
    main()
