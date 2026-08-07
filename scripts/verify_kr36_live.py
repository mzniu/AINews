"""Live smoke test for 36kr AI ingestion source."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.orchestrator import IngestionOrchestrator
from services.ingestion.registry import sync_sources_to_db
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionJob, IngestionSource


def main() -> int:
    init_db()
    factory = get_session_factory()
    with factory() as session:
        sync_sources_to_db(session)
        source = session.get(IngestionSource, "kr36_ai")
        if source is None:
            print("FAIL: kr36_ai source missing")
            return 1
        cfg = json.loads(source.config_json or "{}")
        cfg["max_list_pages"] = 1
        cfg["max_new_articles_per_run"] = 2
        cfg["stop_after_existing"] = 5
        source.config_json = json.dumps(cfg, ensure_ascii=False)
        job = IngestionJob(job_type="verify", source_id="kr36_ai", status="running")
        session.add(job)
        session.flush()
        job_id = job.id
        session.commit()

    print("=== Live 36kr AI ingestion ===")
    try:
        with factory() as session:
            stats = IngestionOrchestrator(session).run_source("kr36_ai", job_id=job_id)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    with factory() as session:
        sync_sources_to_db(session)
        rows = (
            session.query(IngestedArticle)
            .filter_by(source_id="kr36_ai")
            .order_by(IngestedArticle.created_at.desc())
            .limit(2)
            .all()
        )
        for row in rows:
            imgs = session.query(ArticleImage).filter_by(article_id=row.id).all()
            local = sum(1 for i in imgs if i.local_path and Path(i.local_path).exists())
            print(f"\n- {row.title[:70]}")
            print(f"  {row.canonical_url}")
            print(f"  content={len(row.content_text or '')} imgs={len(imgs)} local={local}")

    if stats.get("failed", 0) == 0 and (stats.get("new", 0) > 0 or stats.get("skipped", 0) > 0):
        print("\nPASS")
        return 0
    print("\nFAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
