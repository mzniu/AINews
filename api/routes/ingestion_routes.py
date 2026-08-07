"""资讯入库 API。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Generator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from api.schemas.ingestion_models import (
    BatchSelectRequest,
    BatchScoreRequest,
    IngestedArticleOut,
    IngestionSourceOut,
    JobOut,
    MergeStoriesRequest,
    PrepareVideoResponse,
    ArticleImageOut,
    ScoreArticleRequest,
    ScoreImagesRequest,
    ScoreImagesResponse,
    StoryAssetOut,
    StoryOut,
)
from services.ingestion.bridge import prepare_video_metadata
from services.ingestion.media_job_service import enqueue_media_job
from services.ingestion.media_pipeline import run_media_pipeline
from services.ingestion.image_score_service import score_article_images
from services.ingestion.score_service import apply_score_to_article, score_article_by_id
from services.ingestion.job_enqueue import enqueue_ingestion_job, find_active_ingestion_job
from services.ingestion.job_recovery import recover_stale_jobs
from services.ingestion.registry import sync_sources_to_db
from services.ingestion.settings import (
    build_local_from_public,
    public_ingestion_settings,
    save_ingestion_local,
)
from services.ingestion.story_cluster import expand_story_assets, merge_articles_into_story
from src.db.engine import get_session_factory
from src.db.models.ingestion import (
    ArticleImage,
    CrawlRun,
    ImageRelevanceEvaluation,
    IngestedArticle,
    IngestionJob,
    IngestionSource,
    Story,
    StoryArticle,
    StoryAsset,
)

router = APIRouter(prefix="/api/ingestion", tags=["资讯入库"])


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/sources", response_model=List[IngestionSourceOut])
def list_sources(db: Session = Depends(get_db)):
    sync_sources_to_db(db)
    rows = db.query(IngestionSource).order_by(IngestionSource.id).all()
    return [
        IngestionSourceOut(
            id=r.id,
            slug=r.slug,
            display_name=r.display_name,
            adapter_class=r.adapter_class,
            enabled=r.enabled,
            schedule_cron=r.schedule_cron,
            last_run_at=r.last_run_at,
            last_success_at=r.last_success_at,
            last_error=r.last_error,
        )
        for r in rows
    ]


@router.get("/health")
def ingestion_health(request: Request):
    from services.ingestion.worker import (
        HEARTBEAT_PATH,
        get_ingestion_worker_mode,
        is_embedded_ingestion_worker_running,
    )

    mode = get_ingestion_worker_mode()
    worker_reachable = False
    embedded_worker = getattr(request.app.state, "ingestion_worker", None)
    if mode == "embedded":
        if embedded_worker is not None and embedded_worker.scheduler.running:
            worker_reachable = True
        elif HEARTBEAT_PATH.exists():
            try:
                age = (datetime.utcnow() - datetime.fromisoformat(HEARTBEAT_PATH.read_text(encoding="utf-8"))).total_seconds()
                worker_reachable = age < 90
            except ValueError:
                worker_reachable = False
    elif HEARTBEAT_PATH.exists():
        try:
            age = (datetime.utcnow() - datetime.fromisoformat(HEARTBEAT_PATH.read_text(encoding="utf-8"))).total_seconds()
            worker_reachable = age < 90
        except ValueError:
            worker_reachable = False

    return {
        "success": True,
        "worker_mode": mode,
        "worker_reachable": worker_reachable,
        "embedded_running": is_embedded_ingestion_worker_running(),
    }


@router.get("/settings")
def get_ingestion_settings():
    return {"success": True, **public_ingestion_settings()}


@router.put("/settings")
def update_ingestion_settings(body: dict, request: Request, db: Session = Depends(get_db)):
    try:
        local = build_local_from_public(body)
        save_ingestion_local(local)
        sync_sources_to_db(db)
        worker = getattr(request.app.state, "ingestion_worker", None)
        if worker is not None:
            worker.refresh_schedules()
        return {"success": True, "message": "爬取配置已保存并同步", **public_ingestion_settings()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sources/run-all")
def run_all_sources(db: Session = Depends(get_db)):
    """为所有已启用数据源各提交一个抓取任务。"""
    recover_stale_jobs(db)
    sources = (
        db.query(IngestionSource)
        .filter_by(enabled=True)
        .order_by(IngestionSource.id)
        .all()
    )
    if not sources:
        raise HTTPException(status_code=404, detail="No enabled sources")

    jobs: list[dict] = []
    enqueued = 0
    for source in sources:
        active = find_active_ingestion_job(db, source.id)
        if active:
            jobs.append(
                {
                    "source_id": source.id,
                    "display_name": source.display_name,
                    "job_id": active.id,
                    "status": active.status,
                    "reused": True,
                }
            )
            continue
        job, created = enqueue_ingestion_job(db, source_id=source.id, job_type="manual")
        if job is None:
            continue
        if created:
            enqueued += 1
        jobs.append(
            {
                "source_id": source.id,
                "display_name": source.display_name,
                "job_id": job.id,
                "status": job.status,
                "reused": not created,
            }
        )

    return {
        "success": True,
        "message": f"已为 {len(sources)} 个数据源提交抓取（新增 {enqueued} 个任务）",
        "total_sources": len(sources),
        "enqueued": enqueued,
        "jobs": jobs,
    }


@router.post("/sources/{source_id}/run")
def run_source(source_id: str, db: Session = Depends(get_db)):
    source = db.get(IngestionSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    recover_stale_jobs(db)
    active = find_active_ingestion_job(db, source_id)
    if active is not None:
        message = (
            "已有任务运行中，请稍候或等待 worker 完成"
            if active.status == "running"
            else "任务已在队列中，请等待 worker 执行"
        )
        return {
            "success": True,
            "job_id": active.id,
            "message": message,
            "status": active.status,
        }
    job, _created = enqueue_ingestion_job(db, source_id=source_id, job_type="manual")
    if job is None:
        raise HTTPException(status_code=500, detail="无法创建抓取任务")
    return {
        "success": True,
        "job_id": job.id,
        "message": "已加入队列，请确保 ingestion worker 正在运行",
        "status": job.status,
    }


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(
        id=job.id,
        job_type=job.job_type,
        source_id=job.source_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
    )


@router.get("/runs")
def list_runs(
    source_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(CrawlRun).order_by(CrawlRun.started_at.desc())
    if source_id:
        q = q.filter_by(source_id=source_id)
    rows = q.limit(limit).all()
    return {
        "success": True,
        "runs": [
            {
                "id": r.id,
                "source_id": r.source_id,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "stats": json.loads(r.stats_json or "{}"),
                "error_message": r.error_message,
            }
            for r in rows
        ],
    }


@router.get("/articles")
def list_articles(
    source_id: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = Query(None, description="score_desc | published_desc"),
    min_grade: Optional[str] = Query(None, description="S|A|B|C|D"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if sort == "score_desc":
        query = db.query(IngestedArticle).order_by(
            IngestedArticle.score_total.desc().nullslast(),
            IngestedArticle.published_at.desc().nullslast(),
        )
    else:
        query = db.query(IngestedArticle).order_by(IngestedArticle.published_at.desc().nullslast())
    if source_id:
        query = query.filter_by(source_id=source_id)
    if status:
        query = query.filter_by(status=status)
    if min_grade:
        query = query.filter_by(score_grade=min_grade.upper())
    if q:
        like = f"%{q}%"
        query = query.filter(IngestedArticle.title.like(like))
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "articles": [_article_brief(r, db) for r in rows],
    }


@router.get("/articles/{article_id}", response_model=IngestedArticleOut)
def get_article(article_id: str, db: Session = Depends(get_db)):
    row = db.get(IngestedArticle, article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return _article_full(row, db)


@router.post("/articles/{article_id}/select")
def select_article(article_id: str, db: Session = Depends(get_db)):
    row = db.get(IngestedArticle, article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    row.status = "selected"
    return {"success": True, "article_id": article_id, "status": "selected"}


@router.post("/articles/batch-select")
def batch_select(body: BatchSelectRequest, db: Session = Depends(get_db)):
    updated = 0
    for aid in body.article_ids:
        row = db.get(IngestedArticle, aid)
        if row:
            row.status = "selected"
            updated += 1
    return {"success": True, "updated": updated}


@router.post("/articles/{article_id}/score")
def score_article_endpoint(
    article_id: str,
    body: ScoreArticleRequest,
    db: Session = Depends(get_db),
):
    try:
        result = score_article_by_id(db, article_id, use_llm=body.use_llm)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, **result}


@router.post("/articles/{article_id}/score-images", response_model=ScoreImagesResponse)
def score_images_endpoint(
    article_id: str,
    body: ScoreImagesRequest,
    db: Session = Depends(get_db),
):
    try:
        result = score_article_images(
            db,
            article_id,
            force=body.force,
            include_story_images=body.include_story_images,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        if "视觉模型" in str(exc):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise
    return ScoreImagesResponse(**result)


@router.post("/articles/score-batch")
def score_batch(body: BatchScoreRequest, db: Session = Depends(get_db)):
    if body.article_ids:
        targets = []
        for aid in body.article_ids:
            row = db.get(IngestedArticle, aid)
            if row:
                targets.append(row)
    else:
        query = db.query(IngestedArticle).order_by(IngestedArticle.created_at.desc())
        if body.source_id:
            query = query.filter_by(source_id=body.source_id)
        targets = query.limit(body.limit).all()

    results = []
    for row in targets:
        try:
            results.append(apply_score_to_article(db, row, use_llm=body.use_llm))
        except Exception as exc:
            results.append({"article_id": row.id, "error": str(exc)})
    return {"success": True, "count": len(results), "results": results}


@router.post("/articles/{article_id}/prepare-video", response_model=PrepareVideoResponse)
def prepare_video(
    article_id: str,
    include_story_images: bool = Query(True),
    auto_select: bool = Query(True),
    sort_by_relevance: bool = Query(True),
    db: Session = Depends(get_db),
):
    try:
        result = prepare_video_metadata(
            db,
            article_id,
            include_story_images=include_story_images,
            auto_select=auto_select,
            sort_by_relevance=sort_by_relevance,
        )
        return PrepareVideoResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/articles/{article_id}/media-pipeline/retry")
def retry_media_pipeline(article_id: str, db: Session = Depends(get_db)):
    row = db.get(IngestedArticle, article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    row.media_pipeline_status = None
    row.generated_video_path = None
    row.video_prep_at = None
    if row.score_grade and row.score_total is not None:
        job = enqueue_media_job(
            db,
            article_id,
            trigger_reason="manual_retry",
            final_grade=row.score_grade,
            final_total=float(row.score_total),
        )
        if job:
            db.commit()
            return {"success": True, "enqueued": True, "job_id": job.id}
    try:
        result = run_media_pipeline(db, article_id)
        db.commit()
        return {"success": True, "enqueued": False, **result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stories")
def list_stories(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Story).order_by(Story.updated_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "stories": [_story_brief(r) for r in rows],
    }


@router.get("/stories/{story_id}", response_model=StoryOut)
def get_story(story_id: str, db: Session = Depends(get_db)):
    row = db.get(Story, story_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return _story_brief(row)


@router.get("/stories/{story_id}/articles")
def story_articles(story_id: str, db: Session = Depends(get_db)):
    if db.get(Story, story_id) is None:
        raise HTTPException(status_code=404, detail="Story not found")
    links = db.query(StoryArticle).filter_by(story_id=story_id).all()
    articles = []
    for link in links:
        article = db.get(IngestedArticle, link.article_id)
        if article:
            articles.append(
                {
                    **_article_brief(article, db),
                    "role": link.role,
                    "similarity_score": link.similarity_score,
                }
            )
    return {"success": True, "story_id": story_id, "articles": articles}


@router.get("/stories/{story_id}/assets")
def story_assets(story_id: str, db: Session = Depends(get_db)):
    if db.get(Story, story_id) is None:
        raise HTTPException(status_code=404, detail="Story not found")
    rows = (
        db.query(StoryAsset)
        .filter_by(story_id=story_id)
        .order_by(StoryAsset.sort_order)
        .all()
    )
    return {
        "success": True,
        "story_id": story_id,
        "assets": [_story_asset_out(r) for r in rows],
    }


@router.post("/stories/{story_id}/expand")
def expand_story(story_id: str, db: Session = Depends(get_db)):
    if db.get(Story, story_id) is None:
        raise HTTPException(status_code=404, detail="Story not found")
    count = expand_story_assets(db, story_id)
    return {"success": True, "story_id": story_id, "image_assets": count}


@router.post("/stories/merge")
def merge_stories(body: MergeStoriesRequest, db: Session = Depends(get_db)):
    if len(body.article_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 篇文章")
    try:
        story_id = merge_articles_into_story(db, body.article_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "story_id": story_id}


@router.get("/articles/{article_id}/related")
def related_articles(article_id: str, db: Session = Depends(get_db)):
    article = db.get(IngestedArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    if not article.story_id:
        return {"success": True, "story_id": None, "articles": [], "assets": []}
    links = (
        db.query(StoryArticle)
        .filter_by(story_id=article.story_id)
        .filter(StoryArticle.article_id != article_id)
        .all()
    )
    articles = []
    for link in links:
        other = db.get(IngestedArticle, link.article_id)
        if other:
            articles.append({**_article_brief(other, db), "role": link.role})
    assets = (
        db.query(StoryAsset)
        .filter_by(story_id=article.story_id, asset_type="image")
        .order_by(StoryAsset.sort_order)
        .all()
    )
    return {
        "success": True,
        "story_id": article.story_id,
        "articles": articles,
        "assets": [_story_asset_out(a) for a in assets],
    }


@router.post("/reload-config")
def reload_config(db: Session = Depends(get_db)):
    rows = sync_sources_to_db(db)
    return {"success": True, "count": len(rows)}


def _cover_local_path(db: Session, article_id: str) -> str | None:
    row = (
        db.query(ArticleImage)
        .filter_by(article_id=article_id, download_status="ok")
        .filter(ArticleImage.local_path.isnot(None))
        .order_by(ArticleImage.sort_order)
        .first()
    )
    if row and row.local_path:
        return f"/{row.local_path.lstrip('/')}"
    return None


def _parse_breakdown(row: IngestedArticle) -> dict | None:
    if not row.score_breakdown_json:
        return None
    try:
        return json.loads(row.score_breakdown_json)
    except json.JSONDecodeError:
        return None


def _parse_video_draft(row: IngestedArticle) -> dict | None:
    if not row.video_draft_json:
        return None
    try:
        data = json.loads(row.video_draft_json)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_video_prep_status(row: IngestedArticle) -> dict | None:
    if not row.video_prep_status_json:
        return None
    try:
        data = json.loads(row.video_prep_status_json)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_selected_images(row: IngestedArticle) -> list[dict]:
    if not row.selected_images_json:
        return []
    try:
        data = json.loads(row.selected_images_json)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _article_brief(row: IngestedArticle, db: Session) -> dict:
    img_count = db.query(ArticleImage).filter_by(article_id=row.id).count()
    cover_local = _cover_local_path(db, row.id)
    return {
        "id": row.id,
        "source_id": row.source_id,
        "title": row.title,
        "summary": row.summary,
        "canonical_url": row.canonical_url,
        "published_at": row.published_at,
        "theme": row.theme,
        "status": row.status,
        "cover_image_url": row.cover_image_url,
        "cover_local_path": cover_local,
        "view_count": row.view_count,
        "score_total": row.score_total,
        "score_grade": row.score_grade,
        "score_comment": row.score_comment,
        "scored_at": row.scored_at,
        "image_count": img_count,
        "story_id": row.story_id,
        "created_at": row.created_at,
        "video_draft_generated_at": row.video_draft_generated_at,
        "video_prep_at": row.video_prep_at,
        "video_prep_ready": row.video_prep_at is not None,
        "media_pipeline_status": row.media_pipeline_status,
        "generated_video_path": row.generated_video_path,
        "generated_cover_path": row.generated_cover_path,
        "has_generated_video": bool(row.generated_video_path),
    }


def _evaluation_image_extra(ev: ImageRelevanceEvaluation | None) -> dict:
    if ev is None or not ev.breakdown_json:
        return {}
    try:
        breakdown = json.loads(ev.breakdown_json)
    except json.JSONDecodeError:
        return {}
    dims = breakdown.get("dimensions") or {}
    cover = dims.get("cover_fit") or {}
    figure = dims.get("figure_prominence") or {}
    flash = dims.get("flash_fit") or {}
    width = int(breakdown.get("width") or 0)
    height = int(breakdown.get("height") or 0)
    orientation = None
    if width > 0 and height > 0:
        ratio = width / height
        if ratio >= 1.25:
            orientation = "landscape"
        elif ratio <= 1.0:
            orientation = "portrait"
        else:
            orientation = "square"
    return {
        "cover_fit_score": cover.get("score"),
        "figure_prominence_score": figure.get("score"),
        "flash_fit_score": flash.get("score"),
        "orientation": orientation,
        "is_animated": bool(breakdown.get("is_animated")),
    }


def _article_full(row: IngestedArticle, db: Session) -> IngestedArticleOut:
    images = (
        db.query(ArticleImage)
        .filter_by(article_id=row.id)
        .order_by(ArticleImage.sort_order)
        .all()
    )
    evals = {
        (e.source_type, e.source_id): e
        for e in db.query(ImageRelevanceEvaluation).filter_by(article_id=row.id).all()
    }
    return IngestedArticleOut(
        id=row.id,
        source_id=row.source_id,
        canonical_url=row.canonical_url,
        title=row.title,
        summary=row.summary,
        published_at=row.published_at,
        theme=row.theme,
        status=row.status,
        created_at=row.created_at,
        cover_image_url=row.cover_image_url,
        view_count=row.view_count,
        score_total=row.score_total,
        score_grade=row.score_grade,
        score_breakdown=_parse_breakdown(row),
        score_comment=row.score_comment,
        scored_at=row.scored_at,
        content_text=row.content_text,
        video_draft_generated_at=row.video_draft_generated_at,
        video_prep_at=row.video_prep_at,
        video_draft=_parse_video_draft(row),
        video_prep_status=_parse_video_prep_status(row),
        generated_video_path=row.generated_video_path,
        generated_cover_path=row.generated_cover_path,
        generated_video_at=row.generated_video_at,
        selected_bgm_path=row.selected_bgm_path,
        media_pipeline_status=row.media_pipeline_status,
        selected_images=_parse_selected_images(row),
        images=[
            ArticleImageOut(
                id=i.id,
                original_url=i.original_url,
                local_path=f"/{i.local_path.lstrip('/')}" if i.local_path else None,
                download_status=i.download_status,
                sort_order=i.sort_order,
                relevance_score=ev.relevance_score if (ev := evals.get(("article_image", i.id))) else None,
                relevance_grade=ev.relevance_grade if ev else None,
                relevance_rank=ev.relevance_rank if ev else None,
                caption=ev.caption if ev else None,
                verdict=ev.verdict if ev else None,
                **_evaluation_image_extra(ev if (ev := evals.get(("article_image", i.id))) else None),
            )
            for i in images
        ],
    )


def _story_brief(row: Story) -> StoryOut:
    return StoryOut(
        id=row.id,
        canonical_title=row.canonical_title,
        article_count=row.article_count,
        cluster_method=row.cluster_method,
        cluster_score=row.cluster_score,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _story_asset_out(row: StoryAsset) -> StoryAssetOut:
    payload = {}
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        pass
    local_path = payload.get("local_path")
    return StoryAssetOut(
        id=row.id,
        asset_type=row.asset_type,
        source_article_id=row.source_article_id,
        original_url=payload.get("original_url"),
        local_path=f"/{local_path.lstrip('/')}" if local_path else None,
        download_status=payload.get("download_status"),
        sort_order=row.sort_order,
    )
