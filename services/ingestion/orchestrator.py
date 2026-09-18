"""Ingestion run orchestration."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.ingestion.asset_downloader import get_ingested_root, download_image
from services.ingestion.db_retry import run_with_sqlite_retry, serialized_sqlite_write
from services.ingestion.registry import build_adapter, get_source_config
from services.ingestion.score_service import apply_score_to_article
from services.ingestion.story_cluster import assign_article_to_story
from services.ingestion.url_utils import build_list_page_url, canonicalize_url
from src.db.models.ingestion import ArticleImage, CrawlRun, ImageRelevanceEvaluation, IngestedArticle, IngestionSource, _uuid


def _ingest_cluster_config(cfg: dict) -> dict:
    from services.ingestion.story_cluster_config import load_story_cluster_config

    cluster_cfg = cfg.get("story_cluster") or {}
    options = cfg.get("ingest_performance") or {}
    base = load_story_cluster_config(cluster_cfg)
    if not options.get("story_cluster_llm_on_ingest", False):
        llm = dict(base.get("llm") or {})
        llm["enabled"] = False
        base = {**base, "llm": llm}
    return base


def _is_duplicate_article_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "uq_source_url" in message or "ingested_articles.source_id" in message


def _load_keywords_json(raw: str | None) -> list:
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


class IngestionOrchestrator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _discover_list_with_retry(self, adapter, list_url: str, *, attempts: int = 3):
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                return adapter.discover_list(list_url)
            except Exception as exc:
                last_exc = exc
                logger.warning("discover_list failed (attempt {}/{}): {}", attempt + 1, attempts, exc)
                if attempt + 1 < attempts:
                    time.sleep(1.5 * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    def run_source(self, source_id: str, *, job_id: str | None = None) -> dict:
        source = self.session.get(IngestionSource, source_id)
        if source is None:
            raise ValueError(f"Unknown source: {source_id}")
        cfg = get_source_config(source)
        adapter = build_adapter(source)
        perf = cfg.get("ingest_performance") or {}
        cluster_options = _ingest_cluster_config(cfg)
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
        started = time.perf_counter()

        existing_urls = {
            row[0]
            for row in self.session.query(IngestedArticle.canonical_url)
            .filter_by(source_id=source_id)
            .all()
        }

        try:
            for page in range(1, max_pages + 1):
                if stats["new"] >= max_new:
                    break
                list_url = build_list_page_url(cfg, page)
                refs = self._discover_list_with_retry(adapter, list_url)
                for ref in refs:
                    if stats["new"] >= max_new:
                        break
                    stats["seen"] += 1
                    url = canonicalize_url(ref.url)
                    if url in existing_urls:
                        stats["skipped"] += 1
                        consecutive_existing += 1
                        if consecutive_existing >= stop_after:
                            break
                        continue
                    consecutive_existing = 0
                    try:
                        article = self._ingest_one(
                            source,
                            adapter,
                            ref,
                            run_id,
                            cfg,
                            cluster_options=cluster_options,
                            perf=perf,
                        )
                        existing_urls.add(url)
                        stats["new"] += 1
                    except IntegrityError as exc:
                        self.session.rollback()
                        if _is_duplicate_article_error(exc):
                            existing_urls.add(url)
                            stats["skipped"] += 1
                            continue
                        stats["failed"] += 1
                        stats["errors"].append({"url": url, "error": str(exc)})
                    except Exception as exc:
                        self.session.rollback()
                        stats["failed"] += 1
                        stats["errors"].append({"url": url, "error": str(exc)})
                    if delay > 0:
                        time.sleep(delay)
                if consecutive_existing >= stop_after:
                    break

            run = self.session.get(CrawlRun, run_id)
            source = self.session.get(IngestionSource, source_id)
            if run and source:
                run.status = "partial" if stats["failed"] else "succeeded"
                source.last_run_at = datetime.utcnow()
                if stats["failed"]:
                    source.last_error = f"{stats['failed']} 篇文章抓取失败"
                else:
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
                stats["duration_sec"] = round(time.perf_counter() - started, 2)
                run.stats_json = json.dumps(stats, ensure_ascii=False)
            self.session.commit()
        return stats

    def recrawl_article(self, article_id: str, *, job_id: str | None = None) -> dict:
        """Re-fetch an existing article's detail page and refresh local assets."""
        from services.ingestion.adapters.base import ArticleRef

        article = self.session.get(IngestedArticle, article_id)
        if article is None:
            raise ValueError(f"Article not found: {article_id}")
        source = self.session.get(IngestionSource, article.source_id)
        if source is None:
            raise ValueError(f"Unknown source: {article.source_id}")

        cfg = get_source_config(source)
        adapter = build_adapter(source)
        perf = cfg.get("ingest_performance") or {}
        url = canonicalize_url(article.canonical_url)

        run = CrawlRun(source_id=source.id, job_id=job_id, status="running")
        self.session.add(run)
        self.session.flush()
        run_id = run.id
        self.session.commit()

        stats = {
            "seen": 1,
            "updated": 0,
            "failed": 0,
            "errors": [],
            "article_id": article_id,
        }
        try:
            ref = ArticleRef(url=url, title=article.title or url)
            detail = None
            content_text = article.content_text or ""
            content_html = article.content_html
            try:
                detail = adapter.fetch_detail(ref)
                content_text = detail.content_text or content_text
                content_html = detail.content_html
            except Exception as exc:
                raise RuntimeError(f"fetch_detail failed: {exc}") from exc

            article_dir = get_ingested_root() / source.slug / article_id
            article_dir.mkdir(parents=True, exist_ok=True)
            if content_text:
                content_path = article_dir / "content.txt"
                content_path.write_text(content_text, encoding="utf-8")
                article.content_path = content_path.as_posix()
            if content_html:
                (article_dir / "content.html").write_text(content_html, encoding="utf-8")
                article.content_html = content_html

            metadata = {
                "url": url,
                "title": (detail.title if detail else article.title) or article.title,
                "source_id": source.id,
                "summary": (detail.summary if detail else None) or article.summary,
                "theme": (detail.theme if detail else None) or article.theme,
                "view_count": (
                    detail.view_count
                    if detail and detail.view_count is not None
                    else article.view_count
                ),
            }
            (article_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            image_urls: list[str] = []
            if detail and detail.images:
                image_urls = detail.images
            elif detail and detail.cover_image_url:
                image_urls = [detail.cover_image_url]
            elif article.cover_image_url:
                image_urls = [article.cover_image_url]

            max_images = int(cfg.get("max_images_per_article", 20))
            max_bytes = int(cfg.get("max_image_bytes", 10 * 1024 * 1024))
            images_dir = article_dir / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            for path in images_dir.iterdir():
                if path.is_file():
                    path.unlink()

            self.session.query(ArticleImage).filter_by(article_id=article_id).delete()
            self.session.query(ImageRelevanceEvaluation).filter_by(article_id=article_id).delete()
            article.images_scored_at = None
            article.images_score_summary_json = None

            prep_meta = article_dir / "prepare_video_metadata.json"
            if prep_meta.exists():
                prep_meta.unlink()

            downloaded_images: list[dict] = []
            if cfg.get("download_images", True):
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

            article.title = (detail.title if detail else article.title) or article.title
            article.summary = (detail.summary if detail else None) or article.summary
            article.published_at = (detail.published_at if detail else article.published_at)
            article.theme = (detail.theme if detail else None) or article.theme
            article.keywords_json = json.dumps(
                (detail.keywords if detail and detail.keywords else None)
                or _load_keywords_json(article.keywords_json),
                ensure_ascii=False,
            )
            article.cover_image_url = (
                detail.cover_image_url if detail else article.cover_image_url
            )
            article.view_count = (
                detail.view_count
                if detail and detail.view_count is not None
                else article.view_count
            )
            article.content_text = content_text or None
            article.content_hash = (
                hashlib.sha256(content_text.encode("utf-8")).hexdigest()
                if content_text
                else None
            )
            article.crawl_run_id = run_id
            article.status = "fetched"

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

            serialized_sqlite_write(lambda: self.session.commit())

            try:
                apply_score_to_article(
                    self.session,
                    article,
                    auto_llm_for_sa=bool(perf.get("auto_llm_for_sa_on_ingest", False)),
                )
            except Exception:
                pass
            serialized_sqlite_write(lambda: self.session.commit())

            stats["updated"] = 1
            stats["image_count"] = len(downloaded_images)
            run = self.session.get(CrawlRun, run_id)
            source = self.session.get(IngestionSource, source.id)
            if run and source:
                run.status = "succeeded"
                source.last_success_at = datetime.utcnow()
                source.last_error = None
        except Exception as exc:
            self.session.rollback()
            stats["failed"] = 1
            stats["errors"].append({"url": url, "error": str(exc)})
            run = self.session.get(CrawlRun, run_id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)
        finally:
            run = self.session.get(CrawlRun, run_id)
            if run:
                run.finished_at = datetime.utcnow()
                run.stats_json = json.dumps(stats, ensure_ascii=False)
            self.session.commit()
        return stats

    def ingest_url(
        self,
        source_id: str,
        url: str,
        *,
        title: str | None = None,
        job_id: str | None = None,
    ) -> dict:
        from services.ingestion.adapters.base import ArticleRef

        source = self.session.get(IngestionSource, source_id)
        if source is None:
            raise ValueError(f"Unknown source: {source_id}")
        cfg = get_source_config(source)
        adapter = build_adapter(source)
        perf = cfg.get("ingest_performance") or {}
        cluster_options = _ingest_cluster_config(cfg)
        run = CrawlRun(source_id=source_id, job_id=job_id, status="running")
        self.session.add(run)
        self.session.flush()
        run_id = run.id
        self.session.commit()

        ref = ArticleRef(url=canonicalize_url(url), title=title or url)
        stats = {"seen": 1, "new": 0, "skipped": 0, "failed": 0, "errors": []}
        try:
            article = self._ingest_one(
                source,
                adapter,
                ref,
                run_id,
                cfg,
                cluster_options=cluster_options,
                perf=perf,
            )
            stats["new"] = 1
            stats["article_id"] = article.id
            run = self.session.get(CrawlRun, run_id)
            source = self.session.get(IngestionSource, source_id)
            if run and source:
                run.status = "succeeded"
                source.last_success_at = datetime.utcnow()
                source.last_error = None
        except IntegrityError as exc:
            self.session.rollback()
            if _is_duplicate_article_error(exc):
                stats["skipped"] = 1
                existing = (
                    self.session.query(IngestedArticle)
                    .filter_by(source_id=source_id, canonical_url=canonicalize_url(url))
                    .first()
                )
                if existing is not None:
                    stats["article_id"] = existing.id
            else:
                stats["failed"] = 1
                stats["errors"].append({"url": url, "error": str(exc)})
        except Exception as exc:
            self.session.rollback()
            stats["failed"] = 1
            stats["errors"].append({"url": url, "error": str(exc)})
        finally:
            run = self.session.get(CrawlRun, run_id)
            if run:
                run.finished_at = datetime.utcnow()
                run.stats_json = json.dumps(stats, ensure_ascii=False)
            self.session.commit()
        return stats

    def _ingest_one(
        self,
        source,
        adapter,
        ref,
        run_id: str,
        cfg: dict,
        *,
        cluster_options: dict,
        perf: dict,
    ) -> IngestedArticle:
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
        article_dir = get_ingested_root() / source.slug / article_id
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
        if cfg.get("download_images", True):
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

        from services.industry.profile import get_active_industry_id

        article = IngestedArticle(
            id=article_id,
            source_id=source.id,
            canonical_url=url,
            industry_id=get_active_industry_id(),
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
        serialized_sqlite_write(lambda: self.session.commit())

        if cluster_options.get("enabled", True):
            assign_article_to_story(
                self.session,
                article,
                threshold=float(cluster_options.get("title_threshold", 0.72)),
                hours_window=int(cluster_options.get("hours_window", 72)),
                config=cluster_options,
            )
        try:
            apply_score_to_article(
                self.session,
                article,
                auto_llm_for_sa=bool(perf.get("auto_llm_for_sa_on_ingest", False)),
            )
        except Exception:
            pass
        serialized_sqlite_write(lambda: self.session.commit())
        return article
