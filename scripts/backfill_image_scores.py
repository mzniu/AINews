"""Backfill image relevance scores for ingested articles."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.image_score_backfill import backfill_image_scores
from src.db.engine import get_session_factory, init_db


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Backfill image relevance scores (vision model)")
    parser.add_argument("--source", help="Filter by source_id")
    parser.add_argument("--article-id", help="Score a single article")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--force", action="store_true", help="Ignore cached scores")
    parser.add_argument(
        "--no-story-images",
        action="store_true",
        help="Do not include story-related images",
    )
    args = parser.parse_args()

    init_db()
    factory = get_session_factory()
    with factory() as session:
        summary = backfill_image_scores(
            session,
            source_id=args.source,
            article_id=args.article_id,
            limit=args.limit,
            force=args.force,
            include_story_images=not args.no_story_images,
        )

    print(
        f"Done: processed={summary['processed']} scored={summary['scored']} "
        f"skipped={summary['skipped']} errors={len(summary['errors'])}"
    )
    for item in summary["errors"]:
        print(f"  ERROR {item['article_id']}: {item['error']}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
