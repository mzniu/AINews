"""Re-download failed ingested article images (e.g. qbitai CDN needs Referer)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.asset_downloader import download_image
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import ArticleImage, IngestedArticle


def main(source_id: str = "qbitai") -> int:
    init_db()
    factory = get_session_factory()
    fixed = 0
    with factory() as session:
        rows = (
            session.query(ArticleImage, IngestedArticle)
            .join(IngestedArticle, ArticleImage.article_id == IngestedArticle.id)
            .filter(IngestedArticle.source_id == source_id)
            .filter(ArticleImage.download_status != "ok")
            .all()
        )
        print(f"Retrying {len(rows)} failed images for {source_id}")
        for image, article in rows:
            dest = Path("data/ingested") / article.source_id / article.id / "images"
            result = download_image(
                image.original_url,
                dest,
                index=image.sort_order or 1,
                referer=article.canonical_url,
            )
            if result.get("success"):
                image.local_path = result["local_path"]
                image.download_status = "ok"
                fixed += 1
                print(f"  ok: {image.original_url[:70]}")
            else:
                print(f"  fail: {image.original_url[:70]} -> {result.get('error')}")
        session.commit()
    print(f"Fixed {fixed}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "qbitai"
    raise SystemExit(main(sid))
