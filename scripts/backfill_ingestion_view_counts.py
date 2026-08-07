"""Backfill view_count for ingested articles by re-fetching detail pages."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.adapters.base import ArticleRef
from services.ingestion.registry import build_adapter, get_source_config
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource


def _update_metadata(article: IngestedArticle) -> None:
    if not article.content_path:
        return
    meta_path = Path(article.content_path).parent / "metadata.json"
    if not meta_path.exists():
        return
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        metadata = {}
    metadata["view_count"] = article.view_count
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def backfill(
    *,
    source_id: str | None = None,
    force: bool = False,
    limit: int | None = None,
    delay_sec: float = 2.0,
) -> dict[str, int]:
    init_db()
    factory = get_session_factory()
    stats = {"seen": 0, "updated": 0, "skipped": 0, "failed": 0, "no_metric": 0}

    with factory() as session:
        query = session.query(IngestedArticle).order_by(IngestedArticle.created_at.desc())
        if source_id:
            query = query.filter(IngestedArticle.source_id == source_id)
        if not force:
            query = query.filter(IngestedArticle.view_count.is_(None))
        if limit:
            query = query.limit(limit)

        articles = query.all()
        adapters: dict[str, object] = {}
        configs: dict[str, dict] = {}

        print(f"Backfilling view_count for {len(articles)} article(s)")
        for article in articles:
            stats["seen"] += 1
            source = session.get(IngestionSource, article.source_id)
            if source is None:
                stats["failed"] += 1
                print(f"  skip missing source: {article.id}")
                continue

            if article.source_id not in adapters:
                adapters[article.source_id] = build_adapter(source)
                configs[article.source_id] = get_source_config(source)

            adapter = adapters[article.source_id]
            cfg = configs[article.source_id]
            request_delay = float(cfg.get("request_delay_sec", delay_sec))

            try:
                ref = ArticleRef(url=article.canonical_url, title=article.title or "")
                detail = adapter.fetch_detail(ref)
                if detail.view_count is None:
                    stats["no_metric"] += 1
                    title_preview = (article.title or "")[:40]
                    print(f"  no metric: {article.source_id} {title_preview}")
                else:
                    article.view_count = detail.view_count
                    _update_metadata(article)
                    session.commit()
                    stats["updated"] += 1
                    title_preview = (article.title or "")[:50]
                    print(f"  ok {detail.view_count}: {title_preview}")
            except Exception as exc:
                session.rollback()
                stats["failed"] += 1
                print(f"  fail: {article.canonical_url} -> {exc}")

            if stats["seen"] < len(articles):
                time.sleep(request_delay)

    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Backfill ingested article view counts")
    parser.add_argument("--source", help="Limit to one source_id (e.g. aitnt_travel)")
    parser.add_argument("--force", action="store_true", help="Re-fetch even when view_count exists")
    parser.add_argument("--limit", type=int, help="Max articles to process")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
    args = parser.parse_args()

    stats = backfill(
        source_id=args.source,
        force=args.force,
        limit=args.limit,
        delay_sec=args.delay,
    )
    print(
        f"Done: updated={stats['updated']} no_metric={stats['no_metric']} "
        f"failed={stats['failed']} seen={stats['seen']}"
    )
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
