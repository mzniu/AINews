"""Ingestion run orchestration."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from services.ingestion.asset_downloader import INGESTED_ROOT, download_image
from services.ingestion.db_retry import run_with_sqlite_retry
from services.ingestion.registry import build_adapter, get_source_config
from services.ingestion.score_service import apply_score_to_article
from services.ingestion.story_cluster import assign_article_to_story
from services.ingestion.url_utils import build_list_page_url, canonicalize_url
from src.db.models.ingestion import ArticleImage, CrawlRun, IngestedArticle, IngestionSource, _uuid


class IngestionOrchestrator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run_source(self, source_id: str, *, job_id: str | None = None) -> dict:
        source = self.session.get(IngestionSource, source_id)
        if source is None:
            raise ValueError(f"Unknown source: {source_id}")
        cfg = get_source_config(source)
        adapter = build_adapter(source)
        run = CrawlRun(source_id=source_id, job_id=job_id, status="running")
        self.session.add(run)
        self.session.flush()
        run_id = run.id
        self.session.commit()

        stats = {"seen": 0, "new": 0, "skipped": 0, "failed": 0, "errors": []}
        consecutive_existing = 0
        stop_after = int(cfg.get("stop_after_existing", 5))
        max_pages = int(cfg.get("max_list_pages", 2))
        max_new = int(cfg.get("max_new_articles_per_run", 30))
        delay = float(cfg.get("request_delay_sec", 2))

        try:
            for page in range(1, max_pages + 1):
                if stats["new"] >= max_new:
                    break
                list_url = build_list_page_url(cfg, page)
                refs = adapter.discover_list(list_url)
                for ref in refs:
                    if stats["new"] >= max_new:
                        break
                    stats["seen"] += 1
                    url = canonicalize_url(ref.url)
                    exists = (
                        self.session.query(IngestedArticle)
                        .filter_by(source_id=source_id, canonical_url=url)
                        .first()
                    )
                    if exists:
                        stats["skipped"] += 1
                        consecutive_existing += 1
                        if consecutive_existing >= stop_after:
                            break
                        continue
                    consecutive_existing = 0
                    try:
                        self._ingest_one(source, adapter, ref, run_id, cfg)
                        stats["new"] += 1
                    except Exception as exc:
                        self.session.rollback()
                        stats["failed"] += 1
                        stats["errors"].append({"url": url, "error": str(exc)})
                    time.sleep(delay)
                if consecutive_existing >= stop_after:
                    break

            run = self.session.get(CrawlRun, run_id)
            source = self.session.get(IngestionSource, source_id)
            if run and source:
                run.status = "partial" if stats["failed"] else "succeeded"
                source.last_run_at = datetime.utcnow()
                source.last_success_at = datetime.utcnow()
                source.last_error = None
        except Exception as exc:
            run = self.session.get(CrawlRun, run_id)
            source = self.session.get(IngestionSource, source_id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)
            if source:
                source.last_run_at = datetime.utcnow()
                source.last_error = str(exc)
            stats["errors"].append({"error": str(exc)})
            raise
        finally:
            run = self.session.get(CrawlRun, run_id)
            if run:
                run.finished_at = datetime.utcnow()
                run.stats_json = json.dumps(stats, ensure_ascii=False)
            self.session.commit()
        return stats

    def _ingest_one(self, source, adapter, ref, run_id: str, cfg: dict) -> IngestedArticle:
        url = canonicalize_url(ref.url)
        detail = None
        content_text = ref.summary or ""
        content_html = None
        try:
            detail = adapter.fetch_detail(ref)
            content_text = detail.content_text or content_text
            content_html = detail.content_html
        except Exception:
            detail = None

        article_id = _uuid()
        article_dir = INGESTED_ROOT / source.slug / article_id
        article_dir.mkdir(parents=True, exist_ok=True)
        if content_text:
            content_path = article_dir / "content.txt"
            content_path.write_text(content_text, encoding="utf-8")
        if content_html:
            (article_dir / "content.html").write_text(content_html, encoding="utf-8")
        metadata = {
            "url": url,
            "title": (detail.title if detail else ref.title) or ref.title,
            "source_id": source.id,
            "summary": (detail.summary if detail else None) or ref.summary,
            "theme": (detail.theme if detail else ref.theme) or ref.theme,
            "view_count": (
                detail.view_count
                if detail and detail.view_count is not None
                else ref.view_count
            ),
        }
        (article_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        image_urls: list[str] = []
        if detail and detail.images:
            image_urls = detail.images
        elif ref.cover_image_url:
            image_urls = [ref.cover_image_url]

        max_images = int(cfg.get("max_images_per_article", 20))
        max_bytes = int(cfg.get("max_image_bytes", 10 * 1024 * 1024))
        images_dir = article_dir / "images"
        downloaded_images: list[dict] = []
        for idx, image_url in enumerate(image_urls[:max_images], start=1):
            result = download_image(
                image_url,
                images_dir,
                index=idx,
                max_bytes=max_bytes,
                referer=url,
            )
            downloaded_images.append(
                {
                    "original_url": image_url,
                    "sort_order": idx,
                    "origin": "cover" if idx == 1 else "article_body",
                    "download_status": "ok" if result.get("success") else "failed",
                    "local_path": result.get("local_path"),
                }
            )

        article = IngestedArticle(
            id=article_id,
            source_id=source.id,
            canonical_url=url,
            title=(detail.title if detail else ref.title) or ref.title,
            summary=(detail.summary if detail else None) or ref.summary,
            published_at=(detail.published_at if detail else ref.published_at),
            content_text=content_text or None,
            content_html=content_html,
            theme=(detail.theme if detail else ref.theme) or ref.theme,
            keywords_json=json.dumps(
                (detail.keywords if detail else ref.keywords) or [], ensure_ascii=False
            ),
            cover_image_url=(detail.cover_image_url if detail else ref.cover_image_url),
            view_count=(
                detail.view_count
                if detail and detail.view_count is not None
                else ref.view_count
            ),
            crawl_run_id=run_id,
            status="fetched",
            content_path=(article_dir / "content.txt").as_posix() if content_text else None,
        )
        if article.content_text:
            article.content_hash = hashlib.sha256(article.content_text.encode("utf-8")).hexdigest()
        self.session.add(article)
        for image in downloaded_images:
            self.session.add(
                ArticleImage(
                    article_id=article_id,
                    original_url=image["original_url"],
                    sort_order=image["sort_order"],
                    origin=image["origin"],
                    download_status=image["download_status"],
                    local_path=image["local_path"],
                )
            )
        run_with_sqlite_retry(lambda: self.session.commit())

        cluster_cfg = cfg.get("story_cluster") or {}
        if cluster_cfg.get("enabled", True):
            assign_article_to_story(
                self.session,
                article,
                threshold=float(cluster_cfg.get("title_threshold", 0.72)),
                hours_window=int(cluster_cfg.get("hours_window", 72)),
            )
        try:
            apply_score_to_article(self.session, article, auto_llm_for_sa=True)
        except Exception:
            pass
        run_with_sqlite_retry(lambda: self.session.commit())
        return article
