"""Digital human video generation API routes."""

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from loguru import logger

from services.digital_human_service import digital_human_service


router = APIRouter(prefix="/api/digital-human", tags=["数字人"])


class DigitalHumanGenerateRequest(BaseModel):
    avatar_video: str = Field(..., description="Uploaded avatar video path or /data URL")
    audio_file: str = Field(..., description="Uploaded audio path or /data URL")
    mode: Literal["fast", "ai"] = Field(default="fast", description="Generation mode")
    engine: Literal["auto", "echomimic", "musetalk", "wav2lip"] = Field(default="auto", description="Lip-sync engine")
    use_super_resolution: bool = Field(default=False, description="Reserved for lip-sync engines")
    use_action_generalization: bool = Field(default=False, description="Reserved for lip-sync engines")
    batch_size: int = Field(default=4, ge=1, le=32)


@router.get("/avatars")
async def list_avatars():
    """List uploaded avatar videos and optional MetaHuman reference assets."""
    try:
        return {"success": True, "avatars": digital_human_service.list_avatars()}
    except Exception as exc:
        logger.error(f"列出数字人形象失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/audio")
async def list_audio():
    """List uploaded audio files available for driving."""
    try:
        return {"success": True, "audio": digital_human_service.list_audio()}
    except Exception as exc:
        logger.error(f"列出数字人音频失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/upload-avatar")
async def upload_avatar(file: UploadFile = File(...)):
    """Upload the source video used as the digital human avatar."""
    result = await digital_human_service.save_upload(file, "avatar")
    return {"success": True, "message": "形象视频上传成功", "file": result}


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """Upload the driving audio for digital human generation."""
    result = await digital_human_service.save_upload(file, "audio")
    return {"success": True, "message": "驱动音频上传成功", "file": result}


@router.post("/generate")
async def generate_digital_human(request: DigitalHumanGenerateRequest):
    """Start a digital human generation task."""
    try:
        task = await digital_human_service.create_task(
            avatar_video=request.avatar_video,
            audio_file=request.audio_file,
            mode=request.mode,
            engine=request.engine,
            use_super_resolution=request.use_super_resolution,
            use_action_generalization=request.use_action_generalization,
            batch_size=request.batch_size,
        )
        return {"success": True, "message": "任务已创建", "task": task}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("创建数字人生成任务失败")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/generate-form")
async def generate_digital_human_form(
    avatar_video: str = Form(...),
    audio_file: str = Form(...),
    mode: Literal["fast", "ai"] = Form("fast"),
    engine: Literal["auto", "echomimic", "musetalk", "wav2lip"] = Form("auto"),
    use_super_resolution: bool = Form(False),
    use_action_generalization: bool = Form(False),
    batch_size: int = Form(4),
):
    """Form-compatible generation endpoint for plain HTML clients."""
    request = DigitalHumanGenerateRequest(
        avatar_video=avatar_video,
        audio_file=audio_file,
        mode=mode,
        engine=engine,
        use_super_resolution=use_super_resolution,
        use_action_generalization=use_action_generalization,
        batch_size=batch_size,
    )
    return await generate_digital_human(request)


@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """Get generation progress for a digital human task."""
    return {"success": True, "task": digital_human_service.get_task(task_id)}


@router.get("/engine-status")
async def get_engine_status():
    """Return availability status of each lip-sync engine."""
    from services.lip_sync import lip_sync_engine_manager
    em = lip_sync_engine_manager._echomimic
    mt = lip_sync_engine_manager._musetalk
    wl = lip_sync_engine_manager._wav2lip
    em_reason = em.availability_reason()
    mt_reason = mt.availability_reason()
    wl_reason = wl.availability_reason()
    recommended = (
        "echomimic" if em_reason is None
        else "musetalk" if mt_reason is None
        else "wav2lip" if wl_reason is None
        else None
    )
    return {
        "success": True,
        "engines": {
            "echomimic": {"available": em_reason is None, "reason": em_reason},
            "musetalk": {"available": mt_reason is None, "reason": mt_reason},
            "wav2lip": {"available": wl_reason is None, "reason": wl_reason},
        },
        "recommended": recommended,
    }