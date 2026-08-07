"""One-shot live ingestion smoke test against AITNT travel."""
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
from src.db.models.ingestion import (
    ArticleImage,
    CrawlRun,
    IngestedArticle,
    IngestionJob,
    IngestionSource,
    Story,
    StoryAsset,
)


def main() -> int:
    init_db()
    factory = get_session_factory()
    with factory() as session:
        sync_sources_to_db(session)
        session.commit()

    source_id = "aitnt_travel"
    with factory() as session:
        source = session.get(IngestionSource, source_id)
        if source is None:
            print("FAIL: source aitnt_travel not found after sync")
            return 1
        cfg = json.loads(source.config_json or "{}")
        cfg["max_list_pages"] = 1
        cfg["max_new_articles_per_run"] = 3
        cfg["stop_after_existing"] = 99
        source.config_json = json.dumps(cfg, ensure_ascii=False)
        job = IngestionJob(job_type="verify", source_id=source_id, status="running")
        session.add(job)
        session.flush()
        job_id = job.id
        session.commit()

    print("=== Live ingestion verification ===")
    print(f"Source: {source_id}")
    print("Limits: max_list_pages=1, max_new_articles_per_run=3")
    print("Fetching from travel.aitntnews.com ...")

    try:
        with factory() as session:
            stats = IngestionOrchestrator(session).run_source(source_id, job_id=job_id)
    except Exception as exc:
        print(f"FAIL: orchestrator raised: {exc}")
        return 1

    with factory() as session:
        job = session.get(IngestionJob, job_id)
        if job:
            job.status = "succeeded"
            session.commit()

    print("\n--- Crawl stats ---")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    with factory() as session:
        articles = (
            session.query(IngestedArticle)
            .filter_by(source_id=source_id)
            .order_by(IngestedArticle.created_at.desc())
            .limit(5)
            .all()
        )
        runs = (
            session.query(CrawlRun)
            .filter_by(source_id=source_id)
            .order_by(CrawlRun.started_at.desc())
            .limit(1)
            .all()
        )
        story_count = session.query(Story).count()
        asset_count = session.query(StoryAsset).count()

    print(f"\n--- DB summary ---")
    print(f"Articles (source): {len(articles)} shown / total in run")
    print(f"Stories: {story_count}, Story assets: {asset_count}")
    if runs:
        print(f"Last crawl run: {runs[0].status} @ {runs[0].started_at}")

    if stats.get("new", 0) == 0 and stats.get("seen", 0) == 0:
        print("\nFAIL: no URLs discovered — check network or site structure")
        return 1

    ok = 0
    with factory() as session:
        for row in articles[:3]:
            imgs = session.query(ArticleImage).filter_by(article_id=row.id).all()
            local_imgs = [i for i in imgs if i.local_path and Path(i.local_path).exists()]
            content_ok = bool(row.content_text and len(row.content_text) > 50)
            print(f"\n--- Article: {row.title[:60]}...")
            print(f"  URL: {row.canonical_url}")
            print(f"  Content: {len(row.content_text or '')} chars ({'OK' if content_ok else 'WEAK'})")
            print(f"  Images: {len(imgs)} total, {len(local_imgs)} on disk")
            print(f"  Story: {row.story_id or '—'}")
            if content_ok or row.summary:
                ok += 1
            if local_imgs:
                print(f"  Sample image: {local_imgs[0].local_path}")

    ingested_root = ROOT / "data" / "ingested" / "aitnt_travel"
    dirs = list(ingested_root.glob("*")) if ingested_root.exists() else []
    print(f"\n--- Filesystem ---")
    print(f"data/ingested/aitnt_travel/: {len(dirs)} article dirs")

    if ok >= 1 or stats.get("skipped", 0) > 0:
        print("\nPASS: live crawl verification succeeded")
        with factory() as session:
            sync_sources_to_db(session)
        return 0
    print("\nFAIL: articles lack content")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
