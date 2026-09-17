"""Hot radar admin API routes."""

from __future__ import annotations



from typing import Generator



from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sqlalchemy.orm import Session



from api.schemas.ingestion_models import (
    HotRadarArticleMatchOut,
    HotRadarDiscoveryQueueOut,
    HotRadarSnapshotOut,
)

from services.ingestion.hot_radar_discovery import get_hot_radar_discovery_queue_view
from services.ingestion.hot_radar_service import (

    get_article_hot_radar_view,

    get_hot_radar_snapshot_view,

    refresh_hot_radar,

)

from services.ingestion.hot_radar_settings import (

    load_hot_radar_config,

    public_hot_radar_settings,

    save_hot_radar_settings,

)

from src.db.engine import get_session_factory

from src.db.models.ingestion import IngestedArticle



router = APIRouter(tags=["热榜雷达"])





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





@router.get("/hot-radar/settings")

def get_hot_radar_settings_route():

    return {"success": True, **public_hot_radar_settings()}





@router.put("/hot-radar/settings")

def update_hot_radar_settings_route(body: dict, request: Request):

    try:

        settings = save_hot_radar_settings(body)

        worker = getattr(request.app.state, "ingestion_worker", None)

        if worker is not None:

            worker.refresh_schedules()

        return {"success": True, "message": "热榜雷达配置已保存", **settings}

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc





@router.get("/hot-radar", response_model=HotRadarSnapshotOut)

def get_hot_radar_snapshot(

    refresh: bool = Query(False, description="为 true 时先尝试刷新再返回"),

    db: Session = Depends(get_db),

):

    cfg = load_hot_radar_config()

    if refresh and cfg.get("enabled", True):

        refresh_hot_radar(db, force=True, config=cfg)

    view = get_hot_radar_snapshot_view(db, config=cfg)

    return HotRadarSnapshotOut(**view)





@router.post("/hot-radar/refresh")

def refresh_hot_radar_endpoint(db: Session = Depends(get_db)):

    cfg = load_hot_radar_config()

    result = refresh_hot_radar(db, force=True, config=cfg)

    return {"success": True, **result}


@router.get("/hot-radar/discovery-queue", response_model=HotRadarDiscoveryQueueOut)
def get_hot_radar_discovery_queue(
    limit: int = Query(50, ge=1, le=200),
    hours: int = Query(72, ge=1, le=168),
    db: Session = Depends(get_db),
):
    cfg = load_hot_radar_config()
    view = get_hot_radar_discovery_queue_view(db, limit=limit, hours=hours, config=cfg)
    return HotRadarDiscoveryQueueOut(**view)


@router.get("/hot-radar/articles/{article_id}", response_model=HotRadarArticleMatchOut)

def get_article_hot_radar_match(article_id: str, db: Session = Depends(get_db)):

    row = db.get(IngestedArticle, article_id)

    if row is None:

        raise HTTPException(status_code=404, detail="Article not found")

    view = get_article_hot_radar_view(db, row, config=load_hot_radar_config())

    return HotRadarArticleMatchOut(**view)


legacy_router = APIRouter(tags=["热榜雷达"])


@legacy_router.get("/api/hot-radar/snapshots")
def get_hot_radar_snapshots_legacy(
    limit: int = Query(1, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Backward-compatible shape for older dashboard clients."""
    cfg = load_hot_radar_config()
    view = get_hot_radar_snapshot_view(db, config=cfg)
    items = list(view.get("items") or [])
    snapshot = {**view, "hits": items, "articles": items}
    snapshots = [snapshot][:limit]
    return {"items": snapshots, "snapshots": snapshots}


