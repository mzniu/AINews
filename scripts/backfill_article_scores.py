"""Backfill rule-based scores for ingested articles."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.score_service import apply_score_to_article
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Backfill article scores")
    parser.add_argument("--source", help="Filter by source_id")
    parser.add_argument("--use-llm", action="store_true", help="Also request LLM commentary")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    init_db()
    factory = get_session_factory()
    done = 0
    with factory() as session:
        query = session.query(IngestedArticle).order_by(IngestedArticle.created_at.desc())
        if args.source:
            query = query.filter_by(source_id=args.source)
        rows = query.limit(args.limit).all()
        print(f"Scoring {len(rows)} article(s), llm={args.use_llm}")
        for row in rows:
            result = apply_score_to_article(session, row, use_llm=args.use_llm)
            session.commit()
            done += 1
            title = (row.title or "")[:40]
            print(f"  {result['score_grade']} {result['score_total']:.1f} {title}")
    print(f"Done: {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
