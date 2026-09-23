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
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api.schemas.publishing_models import (
    AccountStatusResponse,
    BindPublishedPostRequest,
    CandidateActionResponse,
    CandidateListResponse,
    PurgeCandidatesRequest,
    PurgeCandidatesResponse,
    CandidateListItem,
    CreatePublishJobRequest,
    ExtractCoverRequest,
    MetricsSyncStatusResponse,
    MetricsAlertsResponse,
    MetricsSummaryResponse,
    PublishedPostResponse,
    PublishJobResponse,
    PublishingHealthResponse,
    QrStartRequest,
    QrStartResponse,
    QrStatusResponse,
    ReschedulePublishJobRequest,
    UpdatePublishPlatformsRequest,
    ViewDropAlert,
    CommentInboxResponse,
    CommentInboxListResponse,
    ApproveCommentReplyRequest,
    CommentReplyRunResponse,
    CommentReplyRunListResponse,
)
from services.publishing.account_delete import AccountDeleteError, delete_publisher_account
from services.publishing.account_status import check_account_status
from services.publishing.compliance import validate_publish_payload
from services.publishing.job_recovery import recover_stale_publish_jobs
from services.publishing.metadata_bridge import PublishDraftMetadata, build_wechat_description
from services.publishing.path_guard import PathGuardError, resolve_cover_path, resolve_video_path, to_relative_posix
from services.publishing.playbook_stamp import playbook_source_from_draft, stamp_playbook
from services.publishing.platform_capabilities import can_account_login, can_video_publish
from services.industry.query_filter import apply_active_industry_filter
from services.publishing.orchestrator import PublishOrchestrator
from services.publishing.qr_login import create_qr_session
from services.publishing.registry import (
    PlatformDisabledError,
    PlatformNotFoundError,
    get_platform_config,
    list_platforms,
)
from src.db.engine import get_session_factory
from src.db.models.ingestion import IngestedArticle
from src.db.models.publishing import (
    AutoPublishCandidate,
    PublishJob,
    PublishLog,
    PublisherAccount,
    QrLoginSession,
    CommentInbox,
    CommentReplyRun,
)
from src.utils.config import Config
from src.utils.paths import resolve_data_path

router = APIRouter(prefix="/api/publishing", tags=["publishing"])

HEARTBEAT_PATH = Config.DATA_DIR / "publish" / "worker_heartbeat"
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
        first_comment_text=job.first_comment_text,
        comment_status=job.comment_status,
        comment_posted_at=job.comment_posted_at,
        comment_error_message=job.comment_error_message,
        comment_retry_count=job.comment_retry_count or 0,
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
        rel = resolve_data_path(row.qr_image_path).resolve().relative_to(Config.DATA_DIR.resolve())
        qr_url = f"/data/{rel.as_posix()}"
    return QrStatusResponse(
        session_id=row.id,
        status=row.status,
        qr_image_url=qr_url,
        account_id=row.account_id,
        error_message=row.error_message,
    )


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, db: Session = Depends(get_db)):
    try:
        summary = delete_publisher_account(db, account_id)
    except AccountDeleteError as exc:
        message = str(exc)
        if "不存在" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=409, detail=message) from exc
    return {"success": True, **summary}


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


def _playbook_source_for_request(db: Session, body: CreatePublishJobRequest) -> dict:
    explicit = {
        "playbook_version_id": body.playbook_version_id,
        "copy_draft_id": body.copy_draft_id,
        "playbook_attribution": body.playbook_attribution,
    }
    if any(explicit.values()):
        return explicit
    if not body.source_id:
        return {}
    article = db.get(IngestedArticle, body.source_id)
    if article is None or not article.video_draft_json:
        return {}
    try:
        data = json.loads(article.video_draft_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return playbook_source_from_draft(data)


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
    first_comment_text = (body.first_comment_text or "").strip() or None
    if first_comment_text:
        from services.publishing.first_comment import validate_first_comment

        ok, err = validate_first_comment(first_comment_text)
        if not ok:
            raise HTTPException(status_code=400, detail=err)
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
        first_comment_text=first_comment_text,
        comment_status="none",
    )
    try:
        stamp_playbook(job, _playbook_source_for_request(db, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"success": True, "job_id": job.id, "status": job.status}


@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = Query(None),
    comment_status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    recover_stale_publish_jobs(db)
    query = db.query(PublishJob).order_by(PublishJob.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    if comment_status:
        query = query.filter(PublishJob.comment_status == comment_status)
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
async def retry_job(
    job_id: str,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    job = db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status not in {"failed", "uploading"}:
        raise HTTPException(status_code=400, detail="仅失败或中断中的任务可重试")
    if not force and job.retry_count >= MAX_RETRY:
        raise HTTPException(
            status_code=400,
            detail=f"已达最大重试次数 {MAX_RETRY}，可添加 ?force=true 强制重试",
        )
    job.status = "pending"
    if not force or job.retry_count < MAX_RETRY:
        job.retry_count += 1
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    db.commit()
    return {
        "success": True,
        "job_id": job.id,
        "status": job.status,
        "retry_count": job.retry_count,
        "forced": force,
    }


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
    out_dir = Config.DATA_DIR / "publish" / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video.stem}_cover.jpg"
    cap = cv2.VideoCapture(str(video))
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise HTTPException(status_code=400, detail="无法读取视频首帧")
    cv2.imwrite(str(out_path), frame)
    return {"success": True, "cover_path": to_relative_posix(out_path)}


@router.get("/auto-publish/settings")
def get_auto_publish_settings_route():
    from services.ingestion.scoring_settings import get_auto_publish_settings

    return {"success": True, **get_auto_publish_settings()}


@router.get("/rollout/status")
def get_rollout_status_route(db: Session = Depends(get_db)):
    from services.publishing.rollout_guard import collect_rollout_status

    return {"success": True, **collect_rollout_status(db)}


@router.get("/rollout/settings")
def get_rollout_settings_route():
    from services.ingestion.scoring_settings import get_publish_policy_settings

    return {"success": True, **get_publish_policy_settings()}


@router.put("/rollout/settings")
def update_rollout_settings_route(body: dict):
    from services.ingestion.scoring_settings import save_publish_policy_settings

    patch: dict = {}
    if "enabled" in body:
        patch["enabled"] = bool(body["enabled"])
    if "shadow_mode" in body:
        patch["shadow_mode"] = bool(body["shadow_mode"])
    platforms = body.get("platforms")
    if isinstance(platforms, dict):
        cleaned = {}
        for platform, raw in platforms.items():
            if not isinstance(raw, dict):
                continue
            entry = {}
            if "enabled" in raw:
                entry["enabled"] = bool(raw["enabled"])
            if "shadow_mode" in raw:
                entry["shadow_mode"] = bool(raw["shadow_mode"])
            if "paused" in raw and platform == "kuaishou":
                # Never force-pause Kuaishou from this control surface.
                entry["paused"] = False
            if entry:
                cleaned[str(platform)] = entry
        if cleaned:
            patch["platforms"] = cleaned
    if not patch:
        raise HTTPException(status_code=400, detail="至少提供一个可更新字段")
    settings = save_publish_policy_settings(patch)
    return {"success": True, **settings}


@router.put("/auto-publish/settings")
def update_auto_publish_settings_route(body: dict):
    from services.ingestion.scoring_settings import save_auto_publish_settings

    allowed = {
        "enabled",
        "min_grade",
        "interval_minutes",
        "quiet_hours_enabled",
        "quiet_hours_start",
        "quiet_hours_end",
    }
    if not any(key in body for key in allowed):
        raise HTTPException(status_code=400, detail="至少提供一个可更新字段")
    try:
        settings = save_auto_publish_settings(
            enabled=body.get("enabled") if "enabled" in body else None,
            min_grade=body.get("min_grade") if "min_grade" in body else None,
            interval_minutes=body.get("interval_minutes") if "interval_minutes" in body else None,
            quiet_hours_enabled=body.get("quiet_hours_enabled")
            if "quiet_hours_enabled" in body
            else None,
            quiet_hours_start=body.get("quiet_hours_start")
            if "quiet_hours_start" in body
            else None,
            quiet_hours_end=body.get("quiet_hours_end") if "quiet_hours_end" in body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "message": "自动发布设置已更新", **settings}


@router.get("/first-comment/settings")
def get_first_comment_settings_route():
    from services.publishing.first_comment_settings import get_first_comment_settings

    return {"success": True, **get_first_comment_settings()}


@router.put("/first-comment/settings")
def update_first_comment_settings_route(body: dict):
    from services.publishing.first_comment_settings import save_first_comment_settings

    if "enabled" not in body:
        raise HTTPException(status_code=400, detail="至少提供 enabled 字段")
    settings = save_first_comment_settings(enabled=bool(body.get("enabled")))
    return {"success": True, "message": "首评设置已更新", **settings}


@router.get("/comment-reply/settings")
def get_comment_reply_settings_route():
    from services.publishing.comment_reply.settings import get_comment_reply_settings

    return {"success": True, **get_comment_reply_settings()}


@router.put("/comment-reply/settings")
def update_comment_reply_settings_route(body: dict):
    from services.publishing.comment_reply.settings import save_comment_reply_settings

    if "enabled" not in body and "mode" not in body and "lookback_hours" not in body:
        raise HTTPException(status_code=400, detail="至少提供 enabled、mode 或 lookback_hours 字段")
    try:
        settings = save_comment_reply_settings(
            enabled=bool(body["enabled"]) if "enabled" in body else None,
            mode=str(body["mode"]) if "mode" in body else None,
            lookback_hours=int(body["lookback_hours"]) if "lookback_hours" in body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "message": "评论回复设置已更新", **settings}


@router.get("/comment-reply/runs", response_model=CommentReplyRunListResponse)
def list_comment_reply_runs(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CommentReplyRun)
        .order_by(CommentReplyRun.started_at.desc())
        .limit(limit)
        .all()
    )
    items = [
        CommentReplyRunResponse(
            id=row.id,
            status=row.status,
            mode=row.mode,
            accounts_total=row.accounts_total,
            posts_scanned=row.posts_scanned,
            comments_seen=row.comments_seen,
            new_pending=row.new_pending,
            auto_sent=row.auto_sent,
            skipped=row.skipped,
            failed=row.failed,
            retried=row.retried,
            error_summary=row.error_summary,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        for row in rows
    ]
    return CommentReplyRunListResponse(items=items, total=len(items))


@router.post("/comment-reply/retry-failed")
async def retry_failed_comment_replies_route():
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

    result = await asyncio.to_thread(
        CommentReplyOrchestrator(get_session_factory()).retry_failed_replies,
    )
    return {"success": True, **result}


@router.post("/comment-reply/regenerate")
async def regenerate_comment_replies_route():
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

    result = await asyncio.to_thread(
        CommentReplyOrchestrator(get_session_factory()).regenerate_pending_replies,
    )
    return {"success": True, **result}


@router.get("/comment-inbox", response_model=CommentInboxListResponse)
def list_comment_inbox(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(CommentInbox).order_by(CommentInbox.created_at.desc())
    if status:
        query = query.filter(CommentInbox.status == status)
    total = query.count()
    rows = query.limit(limit).all()
    account_ids = {row.account_id for row in rows}
    accounts = {
        item.id: item
        for item in db.query(PublisherAccount).filter(PublisherAccount.id.in_(account_ids)).all()
    } if account_ids else {}
    items = [
        CommentInboxResponse(
            id=row.id,
            account_id=row.account_id,
            platform=row.platform,
            platform_post_id=row.platform_post_id,
            platform_comment_id=row.platform_comment_id,
            publish_job_id=row.publish_job_id,
            post_title=row.post_title,
            author_name=row.author_name,
            content=row.content,
            commented_at=row.commented_at,
            status=row.status,
            skip_reason=row.skip_reason,
            reply_text=row.reply_text,
            replied_at=row.replied_at,
            error_message=row.error_message,
            retry_count=row.retry_count or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
            account_nickname=accounts.get(row.account_id).nickname if accounts.get(row.account_id) else None,
        )
        for row in rows
    ]
    return CommentInboxListResponse(items=items, total=total)


@router.post("/comment-inbox/{inbox_id}/approve")
async def approve_comment_inbox_route(
    inbox_id: str,
    body: ApproveCommentReplyRequest,
    db: Session = Depends(get_db),
):
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

    result = await asyncio.to_thread(
        CommentReplyOrchestrator(get_session_factory()).approve_inbox_item,
        inbox_id,
        reply_text=body.reply_text,
    )
    if not result.get("success"):
        error = str(result.get("error") or "approve_failed")
        status_code = 404 if error.endswith("_not_found") else 400
        raise HTTPException(status_code=status_code, detail=error)
    row = db.get(CommentInbox, inbox_id)
    return {"success": True, "status": row.status if row else result.get("status")}


@router.post("/comment-inbox/{inbox_id}/reject")
def reject_comment_inbox_route(inbox_id: str, db: Session = Depends(get_db)):
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

    result = CommentReplyOrchestrator(get_session_factory()).reject_inbox_item(inbox_id)
    if not result.get("success"):
        error = str(result.get("error") or "reject_failed")
        status_code = 404 if error.endswith("_not_found") else 400
        raise HTTPException(status_code=status_code, detail=error)
    row = db.get(CommentInbox, inbox_id)
    return {"success": True, "status": row.status if row else result.get("status")}


@router.post("/comment-reply/scan")
async def trigger_comment_reply_scan_route():
    from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

    summaries = await asyncio.to_thread(
        CommentReplyOrchestrator(get_session_factory()).scan_all_accounts,
        force=True,
    )
    if not summaries:
        return {
            "success": True,
            "accounts": 0,
            "new_pending": 0,
            "message": "未执行扫描：请确认已开启评论回复开关，且存在活跃的视频号账号",
            "summaries": [],
        }
    return {
        "success": True,
        "accounts": len(summaries),
        "new_pending": sum(item.new_pending for item in summaries),
        "auto_sent": sum(item.auto_sent for item in summaries),
        "posts_scanned": sum(item.posts_scanned for item in summaries),
        "comments_seen": sum(item.comments_seen for item in summaries),
        "skipped": sum(item.skipped for item in summaries),
        "errors": sum(item.errors for item in summaries),
        "summaries": [item.__dict__ for item in summaries],
    }


@router.post("/jobs/{job_id}/retry-comment")
async def retry_comment_job_route(
    job_id: str,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    job = db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = await asyncio.to_thread(
        PublishOrchestrator(get_session_factory()).retry_comment_job,
        job_id,
        force=force,
    )
    if not result.get("success") and result.get("error") not in (None, ""):
        error = str(result.get("error") or "")
        if error in {
            "job_not_found",
            "account_not_found",
            "account_inactive",
            "job_not_published",
            "no_comment_text",
            "already_posted",
            "comment_status_not_retryable",
            "retry_limit_reached",
            "unsupported_platform",
        }:
            status_code = 404 if error == "job_not_found" else 400
            raise HTTPException(status_code=status_code, detail=error)
    db.refresh(job)
    return {
        "success": bool(result.get("success")),
        "job_id": job_id,
        "comment_status": result.get("comment_status", job.comment_status),
        "comment_retry_count": result.get("comment_retry_count", job.comment_retry_count),
        "error": result.get("error"),
    }


@router.patch("/jobs/{job_id}/schedule")
async def reschedule_publish_job_route(
    job_id: str,
    body: ReschedulePublishJobRequest,
    db: Session = Depends(get_db),
):
    from services.publishing.schedule import load_spacing_config, reschedule_publish_job

    job = db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        result = reschedule_publish_job(
            db,
            job,
            body.scheduled_at,
            config=load_spacing_config(),
            cascade=body.cascade,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"success": True, **result}


@router.patch("/jobs/{job_id}/platforms")
async def update_publish_platforms_route(
    job_id: str,
    body: UpdatePublishPlatformsRequest,
    db: Session = Depends(get_db),
):
    from services.publishing.platform_jobs import update_job_platforms

    try:
        result = update_job_platforms(db, job_id, body.platforms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"success": True, **result}


@router.get("/published-posts")
def list_published_posts_route(
    platform: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    days: Optional[int] = Query(None, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from services.publishing.metrics.query import list_published_posts

    items, total = list_published_posts(
        db,
        platform=platform,
        account_id=account_id,
        days=days,
        limit=limit,
        offset=offset,
    )
    return {
        "success": True,
        "total": total,
        "posts": [PublishedPostResponse(**item) for item in items],
    }


@router.get("/published-posts/{job_id}/metrics")
def get_published_post_metrics_route(
    job_id: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    from services.publishing.metrics.query import get_post_metrics_history

    job = db.get(PublishJob, job_id)
    if job is None or job.status != "published":
        raise HTTPException(status_code=404, detail="已发布作品不存在")
    history = get_post_metrics_history(db, job_id, days=days)
    return {"success": True, "job_id": job_id, "history": history}


@router.get("/published-posts/export")
def export_published_posts_csv(
    platform: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    days: Optional[int] = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    from services.publishing.metrics.export import build_published_posts_csv

    csv_text = build_published_posts_csv(
        db,
        platform=platform,
        account_id=account_id,
        days=days,
    )
    filename = f"published_posts_{datetime.utcnow():%Y%m%d}.csv"
    return Response(
        content="\ufeff" + csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/published-posts/export.json")
def export_published_posts_json(
    platform: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    days: Optional[int] = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    from services.publishing.metrics.export import build_published_posts_json

    return build_published_posts_json(
        db,
        platform=platform,
        account_id=account_id,
        days=days,
    )


@router.post("/published-posts/{job_id}/bind")
def bind_published_post_route(
    job_id: str,
    body: BindPublishedPostRequest,
    db: Session = Depends(get_db),
):
    from services.publishing.metrics.query import bind_published_post

    try:
        result = bind_published_post(
            db,
            job_id=job_id,
            platform_post_id=body.platform_post_id,
            platform_post_url=body.platform_post_url,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@router.get("/metrics/alerts", response_model=MetricsAlertsResponse)
def get_metrics_alerts_route(
    platform: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    from services.publishing.metrics.alerts import detect_view_drop_alerts
    from services.publishing.metrics.config import load_metrics_sync_config

    cfg = load_metrics_sync_config()
    alerts = detect_view_drop_alerts(
        db,
        drop_pct=cfg["alert_view_drop_pct"],
        min_previous_views=cfg["alert_min_previous_views"],
        days=days,
        platform=platform,
        account_id=account_id,
    )
    return MetricsAlertsResponse(
        success=True,
        alerts=[ViewDropAlert(**item) for item in alerts],
    )


@router.get("/metrics/summary", response_model=MetricsSummaryResponse)
def get_metrics_summary_route(
    platform: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    from services.publishing.metrics.query import get_metrics_summary

    summary = get_metrics_summary(
        db,
        platform=platform,
        account_id=account_id,
        days=days,
    )
    return MetricsSummaryResponse(**summary)


@router.get("/metrics/sync-status", response_model=MetricsSyncStatusResponse)
def get_metrics_sync_status(db: Session = Depends(get_db)):
    from services.publishing.metrics.query import get_latest_sync_run

    run = get_latest_sync_run(db)
    if run is None:
        return MetricsSyncStatusResponse(success=True, status=None)
    return MetricsSyncStatusResponse(
        success=True,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        accounts_total=run.accounts_total,
        posts_synced=run.posts_synced,
        posts_unmatched=run.posts_unmatched,
        posts_failed=run.posts_failed,
        error_summary=run.error_summary,
    )


@router.post("/metrics/sync")
async def trigger_metrics_sync():
    from services.publishing.metrics.sync_orchestrator import MetricsSyncOrchestrator

    factory = get_session_factory()
    run = await asyncio.to_thread(MetricsSyncOrchestrator(factory).sync_all_accounts)
    return {
        "success": True,
        "status": run.status,
        "posts_synced": run.posts_synced,
        "posts_unmatched": run.posts_unmatched,
        "posts_failed": run.posts_failed,
        "error_summary": run.error_summary,
    }


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


@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates_route(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    recommended_action: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("priority"),
    db: Session = Depends(get_db),
):
    from sqlalchemy import desc as sa_desc, asc as sa_asc

    query = apply_active_industry_filter(db.query(AutoPublishCandidate), AutoPublishCandidate)
    if platform:
        query = query.filter(AutoPublishCandidate.platform == platform)
    if status:
        query = query.filter(AutoPublishCandidate.status == status)
    if recommended_action:
        query = query.filter(AutoPublishCandidate.recommended_action == recommended_action)

    total = query.count()

    sort_column_map = {
        "priority": AutoPublishCandidate.priority,
        "evaluated_at": AutoPublishCandidate.evaluated_at,
        "created_at": AutoPublishCandidate.created_at,
    }
    sort_column = sort_column_map.get(sort_by or "priority", AutoPublishCandidate.priority)
    if sort_by == "priority":
        query = query.order_by(sa_desc(sort_column), AutoPublishCandidate.evaluated_at.asc())
    else:
        query = query.order_by(sa_desc(sort_column))

    rows = query.offset((page - 1) * per_page).limit(per_page).all()

    def _candidate_title(row: AutoPublishCandidate) -> str:
        article = db.query(IngestedArticle).filter(IngestedArticle.id == row.article_id).first()
        return (article.title or "未命名") if article else "未命名"

    items = []
    for row in rows:
        try:
            reasons = json.loads(row.reasons_json or "[]")
        except (TypeError, json.JSONDecodeError):
            reasons = []
        items.append(
            CandidateListItem(
                id=row.id,
                article_id=row.article_id,
                title=_candidate_title(row),
                platform=row.platform,
                action=row.action,
                recommended_action=row.recommended_action,
                priority=row.priority,
                reasons=reasons,
                status=row.status,
                evaluated_at=row.evaluated_at,
                created_at=row.created_at,
            )
        )
    return CandidateListResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/candidates/purge", response_model=PurgeCandidatesResponse)
def purge_candidates_route(body: PurgeCandidatesRequest, db: Session = Depends(get_db)):
    from services.publishing.candidate_queue import purge_stale_candidates

    deleted = purge_stale_candidates(db, older_than_days=body.older_than_days)
    db.commit()
    return PurgeCandidatesResponse(
        success=True,
        deleted=deleted,
        older_than_days=body.older_than_days,
    )


@router.post("/candidates/{candidate_id}/skip", response_model=CandidateActionResponse)
def skip_candidate_route(candidate_id: str, db: Session = Depends(get_db)):
    from services.publishing.candidate_queue import skip_candidate as skip_candidate_service
    try:
        candidate = skip_candidate_service(db, candidate_id)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CandidateActionResponse(success=True, candidate_id=candidate_id, status=candidate.status)


@router.post("/candidates/{candidate_id}/enqueue", response_model=CandidateActionResponse)
def enqueue_candidate_route(candidate_id: str, db: Session = Depends(get_db)):
    from services.publishing.candidate_queue import enqueue_candidate as enqueue_candidate_service
    from services.ingestion.article_scorer import load_scoring_config
    try:
        config = load_scoring_config()
        candidate = enqueue_candidate_service(db, candidate_id, config=config)
        db.commit()
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return CandidateActionResponse(
        success=True,
        candidate_id=candidate_id,
        status=candidate.status,
        publish_job_id=candidate.publish_job_id,
    )
