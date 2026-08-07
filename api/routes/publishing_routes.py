"""Publishing API routes."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from api.schemas.publishing_models import (
    AccountStatusResponse,
    CreatePublishJobRequest,
    ExtractCoverRequest,
    PublishJobResponse,
    PublishingHealthResponse,
    QrStartRequest,
    QrStartResponse,
    QrStatusResponse,
)
from services.publishing.account_status import check_account_status
from services.publishing.compliance import validate_publish_payload
from services.publishing.job_recovery import recover_stale_publish_jobs
from services.publishing.metadata_bridge import PublishDraftMetadata, build_wechat_description
from services.publishing.path_guard import PathGuardError, resolve_cover_path, resolve_video_path, to_relative_posix
from services.publishing.platform_capabilities import can_account_login, can_video_publish
from services.publishing.qr_login import create_qr_session
from services.publishing.registry import (
    PlatformDisabledError,
    PlatformNotFoundError,
    get_platform_config,
    list_platforms,
)
from src.db.engine import get_session_factory
from src.db.models.publishing import PublishJob, PublishLog, PublisherAccount, QrLoginSession
from src.utils.config import Config

router = APIRouter(prefix="/api/publishing", tags=["publishing"])

HEARTBEAT_PATH = Config.ROOT_DIR / "data" / "publish" / "worker_heartbeat"
MAX_RETRY = 3


def get_db():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _job_to_response(job: PublishJob, account: PublisherAccount | None = None) -> PublishJobResponse:
    platform = account.platform if account else None
    platform_display_name = None
    if platform:
        try:
            platform_display_name = get_platform_config(platform).get("display_name", platform)
        except PlatformNotFoundError:
            platform_display_name = platform
    return PublishJobResponse(
        id=job.id,
        account_id=job.account_id,
        platform=platform,
        platform_display_name=platform_display_name,
        account_nickname=account.nickname if account else None,
        video_path=job.video_path,
        title=job.title,
        description=job.description,
        tags=json.loads(job.tags_json or "[]"),
        cover_path=job.cover_path,
        status=job.status,
        platform_post_id=job.platform_post_id,
        error_message=job.error_message,
        retry_count=job.retry_count,
        source_type=job.source_type,
        source_id=job.source_id,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        published_at=job.published_at,
        scheduled_at=job.scheduled_at,
    )


@router.get("/platforms")
async def get_platforms():
    return {"success": True, "platforms": list_platforms()}


@router.get("/accounts")
async def get_accounts(db: Session = Depends(get_db)):
    rows = db.query(PublisherAccount).order_by(PublisherAccount.created_at.desc()).all()
    accounts = []
    for row in rows:
        try:
            cfg = get_platform_config(row.platform)
            platform_display_name = cfg.get("display_name", row.platform)
        except PlatformNotFoundError:
            platform_display_name = row.platform
        accounts.append(
            {
                "id": row.id,
                "platform": row.platform,
                "platform_display_name": platform_display_name,
                "nickname": row.nickname,
                "avatar_url": row.avatar_url,
                "status": row.status,
                "can_publish": can_video_publish(row.platform),
                "last_login_at": row.last_login_at,
                "last_publish_at": row.last_publish_at,
            }
        )
    return {"success": True, "accounts": accounts}


@router.post("/accounts/qr-start", response_model=QrStartResponse)
async def qr_start(body: QrStartRequest, db: Session = Depends(get_db)):
    try:
        cfg = get_platform_config(body.platform)
    except PlatformNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not cfg.get("enabled", False):
        raise HTTPException(status_code=400, detail=f"平台未启用: {body.platform}")
    if not can_account_login(body.platform):
        raise HTTPException(status_code=400, detail="该平台暂不支持账号登录")
    if body.purpose == "refresh" and not body.account_id:
        raise HTTPException(status_code=400, detail="refresh 需要 account_id")
    row = create_qr_session(
        db,
        platform=body.platform,
        purpose=body.purpose,
        account_id=body.account_id,
    )
    return QrStartResponse(session_id=row.id)


@router.get("/accounts/qr-status/{session_id}", response_model=QrStatusResponse)
async def qr_status(session_id: str, db: Session = Depends(get_db)):
    row = db.get(QrLoginSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    qr_url = None
    if row.qr_image_path:
        rel = Path(row.qr_image_path)
        try:
            rel = rel.resolve().relative_to(Config.ROOT_DIR.resolve())
        except ValueError:
            rel = Path(row.qr_image_path)
        qr_url = f"/{rel.as_posix()}"
    return QrStatusResponse(
        session_id=row.id,
        status=row.status,
        qr_image_url=qr_url,
        account_id=row.account_id,
        error_message=row.error_message,
    )


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, db: Session = Depends(get_db)):
    row = db.get(PublisherAccount, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    session_file = Config.ROOT_DIR / row.session_path
    db.delete(row)
    db.commit()
    if session_file.exists():
        session_file.unlink()
    return {"success": True}


@router.post("/accounts/{account_id}/check-status", response_model=AccountStatusResponse)
async def check_account_status_endpoint(account_id: str):
    try:
        result = await asyncio.to_thread(check_account_status, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AccountStatusResponse(**result)


@router.post("/accounts/{account_id}/refresh", response_model=QrStartResponse)
async def refresh_account(account_id: str, db: Session = Depends(get_db)):
    row = db.get(PublisherAccount, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    session = create_qr_session(
        db,
        platform=row.platform,
        purpose="refresh",
        account_id=account_id,
    )
    return QrStartResponse(session_id=session.id)


def _resolve_job_description(body: CreatePublishJobRequest) -> str | None:
    text = (body.description or "").strip()
    if text:
        return text
    structured = any(
        [
            (body.main_line2 or "").strip(),
            (body.sub_title or "").strip(),
            (body.sub_title2 or "").strip(),
            (body.summary or "").strip(),
        ]
    )
    if structured or body.tags:
        draft = PublishDraftMetadata(
            main_line2=body.main_line2 or "",
            sub_title=body.sub_title or "",
            sub_title2=body.sub_title2 or "",
            summary=body.summary or "",
            praise_tags=body.tags,
            tags=body.tags,
        )
        return build_wechat_description(draft).strip() or None
    return None


@router.post("/jobs")
async def create_job(body: CreatePublishJobRequest, db: Session = Depends(get_db)):
    account = db.get(PublisherAccount, body.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if account.status != "active":
        raise HTTPException(status_code=400, detail="账号不可用，请重新登录")
    if not can_video_publish(account.platform):
        raise HTTPException(status_code=400, detail="该平台自动发布尚未开放")
    try:
        video = resolve_video_path(body.video_path)
    except PathGuardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cover_rel: str | None = None
    if body.cover_path:
        try:
            cover = resolve_cover_path(body.cover_path)
            cover_rel = to_relative_posix(cover) if cover else None
        except PathGuardError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    description = _resolve_job_description(body)
    compliance = validate_publish_payload(body.title, description, body.tags)
    if not compliance.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "发布内容命中禁限词",
                "violations": [item.to_dict() for item in compliance.violations],
            },
        )
    scheduled_at = body.scheduled_at
    if scheduled_at is not None:
        if scheduled_at.tzinfo is not None:
            scheduled_at = scheduled_at.replace(tzinfo=None)
        if scheduled_at <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="定时发布时间必须晚于当前时间")
    job = PublishJob(
        account_id=body.account_id,
        video_path=to_relative_posix(video),
        title=body.title.strip(),
        description=description,
        tags_json=json.dumps(body.tags, ensure_ascii=False),
        cover_path=cover_rel,
        source_type=body.source_type,
        source_id=body.source_id,
        status="pending",
        scheduled_at=scheduled_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"success": True, "job_id": job.id, "status": job.status}


@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    recover_stale_publish_jobs(db)
    query = db.query(PublishJob).order_by(PublishJob.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    rows = query.offset(offset).limit(limit).all()
    account_map: dict[str, PublisherAccount] = {}
    if rows:
        account_ids = [row.account_id for row in rows]
        account_map = {
            account.id: account
            for account in db.query(PublisherAccount)
            .filter(PublisherAccount.id.in_(account_ids))
            .all()
        }
    return {
        "success": True,
        "jobs": [_job_to_response(row, account_map.get(row.account_id)) for row in rows],
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    logs = (
        db.query(PublishLog)
        .filter_by(job_id=job_id)
        .order_by(PublishLog.created_at.asc())
        .all()
    )
    payload = _job_to_response(job, db.get(PublisherAccount, job.account_id)).model_dump()
    payload["logs"] = [
        {
            "id": log.id,
            "level": log.level,
            "message": log.message,
            "screenshot_path": log.screenshot_path,
            "created_at": log.created_at,
        }
        for log in logs
    ]
    return {"success": True, "job": payload}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status not in {"failed", "uploading"}:
        raise HTTPException(status_code=400, detail="仅失败或中断中的任务可重试")
    if job.retry_count >= MAX_RETRY:
        raise HTTPException(status_code=400, detail=f"已达最大重试次数 {MAX_RETRY}")
    job.status = "pending"
    job.retry_count += 1
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    db.commit()
    return {"success": True, "job_id": job.id, "status": job.status}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status not in {"pending", "uploading"}:
        raise HTTPException(status_code=400, detail="仅待发布或上传中的任务可取消")
    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.post("/extract-cover")
async def extract_cover(body: ExtractCoverRequest):
    try:
        video = resolve_video_path(body.video_path)
    except PathGuardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out_dir = Config.ROOT_DIR / "data" / "publish" / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video.stem}_cover.jpg"
    cap = cv2.VideoCapture(str(video))
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise HTTPException(status_code=400, detail="无法读取视频首帧")
    cv2.imwrite(str(out_path), frame)
    return {"success": True, "cover_path": to_relative_posix(out_path)}


@router.get("/health", response_model=PublishingHealthResponse)
async def publishing_health(request: Request, db: Session = Depends(get_db)):
    from services.publishing.worker import get_publish_worker_mode

    mode = get_publish_worker_mode()
    worker_reachable = False
    embedded_worker = getattr(request.app.state, "publish_worker", None)
    if mode == "embedded":
        if embedded_worker is not None and embedded_worker.scheduler.running:
            worker_reachable = True
        elif HEARTBEAT_PATH.exists():
            age = time.time() - HEARTBEAT_PATH.stat().st_mtime
            worker_reachable = age < 90
    elif HEARTBEAT_PATH.exists():
        age = time.time() - HEARTBEAT_PATH.stat().st_mtime
        worker_reachable = age < 90
    pending = db.query(PublishJob).filter_by(status="pending").order_by(PublishJob.created_at.asc()).all()
    oldest_seconds = None
    if pending:
        oldest = pending[0].created_at
        if oldest:
            oldest_seconds = (datetime.utcnow() - oldest).total_seconds()
    return PublishingHealthResponse(
        worker_mode=mode,
        worker_reachable=worker_reachable,
        pending_jobs_count=len(pending),
        oldest_pending_seconds=oldest_seconds,
    )
