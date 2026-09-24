"""Learning-loop HTTP: harness check, curate, and publishing a playbook version."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from services.copy_agent.battle_report import build_battle_report
from services.copy_agent.progress import read_live_session_text
from services.copy_agent.session_log import summarize_session_log
from services.copy_agent.versions import get_playbook_version, list_playbook_versions
from src.utils.paths import get_data_dir
import threading

from services.copy_agent.curate import (
    SUMMARY_ESCAPE,
    SUMMARY_OK,
    begin_curate,
    dsh_sdk_installed,
    execute_curate_job,
    start_dsh,
)
from services.copy_agent.drafts import (
    DraftNotSelectable,
    NoPlaybook,
    draft_selectable,
    draft_stamp_source,
    generate_one_draft,
    playbook_selection_fields,
    select_draft,
)
from services.copy_agent.pattern_ranking import (
    TooManyPatterns,
    production_rank_complete,
    rank_playbook_for_material,
    ranked_rows_for_api,
    selection_for_api,
)
from services.copy_agent.settings_store import (
    AutoSwitchBlocksPublish,
    TrapCheckFailed,
    get_settings,
    publish_version,
    set_auto_material_adaptive,
    set_auto_switch,
    set_fact_gate_enabled,
    set_material_adaptive,
    set_ranking_max_candidates,
)
from src.db.engine import get_session_factory
from src.db.models.playbook import CopyAgentJob

router = APIRouter(prefix="/api/copy-agent", tags=["打法学习"])

_NOT_READY = [
    "还不能拆爆款。未检测到 dsh。",
    "安装 deepseek-harness-sdk 后点重新检测。",
    "检测通过后会出现贴文框。",
]
_READY = [
    "可以拆卡。",
    "把屏幕上的文案贴进来。",
    "拆完后可以发布为当前打法。",
]


def dsh_installed() -> bool:
    return dsh_sdk_installed()


def production_runner(workspace, session_root, session_id, env):
    start_dsh(workspace, session_root, session_id, env)


class MaterialBody(BaseModel):
    text: str = ""
    include_battle: bool = False


class AutoSwitchBody(BaseModel):
    enabled: bool


class RankingSettingsBody(BaseModel):
    material_adaptive_playbook: bool | None = None
    auto_material_adaptive_playbook: bool | None = None
    ranking_max_candidates: int | None = None
    fact_gate_enabled: bool | None = None


class DraftBody(BaseModel):
    title: str = ""
    content: str = ""


class RankPreviewBody(BaseModel):
    title: str = ""
    content: str = ""
    article_id: str | None = None


class SelectDraftBody(BaseModel):
    edited: bool = False


@router.get("/harness")
def harness_status():
    ready = dsh_installed()
    return {"ready": ready, "lines": _READY if ready else _NOT_READY}


@router.post("/materials")
def create_material(body: MaterialBody):
    session = get_session_factory()()
    try:
        running = (
            session.query(CopyAgentJob)
            .filter_by(kind="curate", status="running")
            .first()
        )
        if running is not None:
            return JSONResponse(
                status_code=409,
                content={"message": "已有拆卡任务在跑", "job_id": running.id},
            )
        job = begin_curate(session, text=body.text, include_battle=body.include_battle)
        if job.status != "running":
            return {"job_id": job.id, "status": job.status}
        job_id = job.id
    finally:
        session.close()

    threading.Thread(
        target=execute_curate_job,
        args=(job_id,),
        kwargs={"runner": production_runner},
        name=f"curate-{job_id}",
        daemon=True,
    ).start()
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/active")
def active_curate_job():
    session = get_session_factory()()
    try:
        job = (
            session.query(CopyAgentJob)
            .filter_by(kind="curate", status="running")
            .order_by(CopyAgentJob.created_at.desc())
            .first()
        )
        if job is None:
            return {"job_id": None}
        return {"job_id": job.id, "status": job.status}
    finally:
        session.close()


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    session = get_session_factory()()
    try:
        job = session.get(CopyAgentJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        payload = json.loads(job.result_json or "{}")
        summary = payload.get("summary") or ""
        if job.status == "rejected_escape":
            summary = SUMMARY_ESCAPE
        elif job.status == "candidate" and not summary:
            summary = SUMMARY_OK
        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        return {
            "job_id": job.id,
            "status": job.status,
            "summary": summary,
            "playbook_version_id": payload.get("playbook_version_id"),
            "paths": payload.get("paths") or [],
            "progress": progress,
            "trap_passed": payload.get("trap_passed"),
            "card_preview": payload.get("card_preview"),
            "playbook_body": payload.get("playbook_body"),
            "schema_issues": payload.get("schema_issues") or [],
            "body_issues": payload.get("body_issues") or [],
            "turn_end_reason": payload.get("turn_end_reason"),
        }
    finally:
        session.close()


@router.get("/versions")
def list_versions():
    session = get_session_factory()()
    try:
        return list_playbook_versions(session)
    finally:
        session.close()


@router.get("/versions/{version_id}")
def version_detail(version_id: str):
    session = get_session_factory()()
    try:
        detail = get_playbook_version(session, version_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="打法版本不存在")
        return detail
    finally:
        session.close()


@router.get("/jobs/{job_id}/log")
def job_session_log(job_id: str):
    session = get_session_factory()()
    try:
        job = session.get(CopyAgentJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        session_root = get_data_dir() / "copy_agent" / "sessions" / job.id
        log_text = read_live_session_text(session_root)
        if not log_text.strip():
            return {"job_id": job.id, "entries": [], "text": "（这次没有保存到会话记录）"}
        return {"job_id": job.id, **summarize_session_log(log_text)}
    finally:
        session.close()


@router.post("/versions/{version_id}/publish")
def publish_current(version_id: str):
    session = get_session_factory()()
    try:
        publish_version(session, version_id)
        return {"success": True, "current_playbook_version_id": version_id}
    except AutoSwitchBlocksPublish as exc:
        return JSONResponse(
            status_code=409,
            content={"message": str(exc), "hint": "disable_auto_switch"},
        )
    finally:
        session.close()


@router.post("/auto-switch")
def auto_switch(body: AutoSwitchBody):
    session = get_session_factory()()
    try:
        set_auto_switch(session, body.enabled)
        return {"success": True, "enabled": body.enabled}
    except TrapCheckFailed as exc:
        return JSONResponse(status_code=409, content={"message": str(exc)})
    finally:
        session.close()


def production_complete(messages: list[dict]) -> str:
    from services.content_generation_service import _build_openai_client
    from utils.content_compliance import invoke_json_llm_with_compliance
    import os

    client, model, _base_url, profile = _build_openai_client()
    result, _compliance = invoke_json_llm_with_compliance(
        client=client,
        model=model,
        messages=messages,
        temperature=0.85,
        max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192")),
        response_format={"type": "json_object"},
        profile=profile,
        task="content_gen",
    )
    return json.dumps(result, ensure_ascii=False)


@router.post("/rank-preview")
def rank_preview(body: RankPreviewBody):
    session = get_session_factory()()
    try:
        settings = get_settings(session)
        selection = rank_playbook_for_material(
            session,
            title=body.title,
            content=body.content,
            complete_rank=production_rank_complete,
            adaptive=bool(settings.material_adaptive_playbook),
            current_version_id=settings.current_playbook_version_id,
            max_candidates=int(settings.ranking_max_candidates or 40),
            article_id=body.article_id,
            use_selection_cache=False,
        )
        return {
            "success": True,
            "material_adaptive_playbook": bool(settings.material_adaptive_playbook),
            "selection": selection_for_api(selection),
            "ranked": ranked_rows_for_api(session, selection),
            "candidates_count": selection.get("candidates_count") or 0,
            "prefiltered_from": selection.get("prefiltered_from"),
        }
    except NoPlaybook as exc:
        return JSONResponse(status_code=409, content={"message": str(exc), "hint": "no_playbook"})
    except TooManyPatterns as exc:
        return JSONResponse(status_code=409, content={"message": str(exc)})
    except (ValueError, json.JSONDecodeError) as exc:
        return JSONResponse(
            status_code=422,
            content={"message": f"Ranking 结果无法解析：{exc}"},
        )
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"message": str(exc)})
    except Exception as exc:
        logger.exception("rank-preview failed")
        return JSONResponse(
            status_code=502,
            content={"message": f"Ranking 调用失败：{exc}"},
        )
    finally:
        session.close()


@router.get("/patterns")
def pattern_library():
    from services.copy_agent.pattern_library import list_pattern_library

    session = get_session_factory()()
    try:
        return list_pattern_library(session)
    finally:
        session.close()


@router.get("/battle-report")
def battle_report():
    session = get_session_factory()()
    try:
        return build_battle_report(session)
    finally:
        session.close()


@router.get("/settings")
def copy_settings():
    session = get_session_factory()()
    try:
        settings = get_settings(session)
        session.commit()
        return {
            "has_current": bool(settings.current_playbook_version_id),
            "current_playbook_version_id": settings.current_playbook_version_id,
            "auto_uses_current_playbook": settings.auto_uses_current_playbook,
            "material_adaptive_playbook": settings.material_adaptive_playbook,
            "auto_material_adaptive_playbook": settings.auto_material_adaptive_playbook,
            "ranking_max_candidates": settings.ranking_max_candidates,
            "fact_gate_enabled": settings.fact_gate_enabled,
        }
    finally:
        session.close()


@router.patch("/settings")
def patch_copy_settings(body: RankingSettingsBody):
    session = get_session_factory()()
    try:
        if body.material_adaptive_playbook is not None:
            set_material_adaptive(session, body.material_adaptive_playbook)
        if body.auto_material_adaptive_playbook is not None:
            set_auto_material_adaptive(session, body.auto_material_adaptive_playbook)
        if body.ranking_max_candidates is not None:
            set_ranking_max_candidates(session, body.ranking_max_candidates)
        if body.fact_gate_enabled is not None:
            set_fact_gate_enabled(session, body.fact_gate_enabled)
        settings = get_settings(session)
        return {
            "success": True,
            "material_adaptive_playbook": settings.material_adaptive_playbook,
            "auto_material_adaptive_playbook": settings.auto_material_adaptive_playbook,
            "ranking_max_candidates": settings.ranking_max_candidates,
            "fact_gate_enabled": settings.fact_gate_enabled,
        }
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"message": str(exc)})
    finally:
        session.close()


@router.post("/drafts")
def create_draft(body: DraftBody):
    session = get_session_factory()()
    try:
        draft = generate_one_draft(
            session,
            title=body.title,
            content=body.content,
            complete=production_complete,
            complete_rank=production_rank_complete,
        )
        gate = json.loads(draft.fact_gate_json or "{}")
        return {
            "draft_id": draft.id,
            "selectable": draft_selectable(draft),
            "text": json.loads(draft.body_json or "{}").get("text") or "",
            "fact_gate": gate,
            "playbook_version_id": draft.playbook_version_id,
            "selection": playbook_selection_fields(draft),
        }
    except NoPlaybook as exc:
        return JSONResponse(
            status_code=409,
            content={"hint": "no_playbook", "message": str(exc)},
        )
    finally:
        session.close()


@router.post("/drafts/{draft_id}/select")
def select_current_draft(draft_id: str, body: SelectDraftBody):
    session = get_session_factory()()
    try:
        draft = select_draft(session, draft_id, edited=body.edited)
        return {
            "draft_id": draft.id,
            "selected": draft.selected,
            "edited": draft.edited_after_select,
            "playbook_version_id": draft.playbook_version_id,
            "stamp": draft_stamp_source(draft),
        }
    except DraftNotSelectable as exc:
        return JSONResponse(status_code=409, content={"message": str(exc), "hint": "not_selectable"})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        session.close()
