"""Quick post-crawl verification helpers."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from src.db.engine import get_session_factory, init_db
from services.ingestion.bridge import prepare_video_metadata
from src.db.models.ingestion import IngestedArticle, ArticleImage, CrawlRun

init_db()
factory = get_session_factory()
with factory() as session:
    articles = (
        session.query(IngestedArticle)
        .order_by(IngestedArticle.created_at.desc())
        .limit(3)
        .all()
    )
    print("=== DB articles (UTF-8) ===")
    for article in articles:
        img_count = session.query(ArticleImage).filter_by(article_id=article.id).count()
        print(f"- {article.title[:80]}")
        print(f"  id={article.id} imgs={img_count} story={article.story_id}")
    run = session.query(CrawlRun).order_by(CrawlRun.started_at.desc()).first()
    print(f"\nLast run: {run.status} stats={run.stats_json}")
    prep = prepare_video_metadata(session, articles[0].id)
    print(f"\n=== prepare-video ===")
    print(f"title: {prep['title'][:60]}")
    print(f"images: {len(prep['images'])}")
    print(f"metadata_path: {prep['metadata_path']}")
