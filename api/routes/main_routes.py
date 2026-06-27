"""主要页面路由"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path
from datetime import datetime
from loguru import logger
import os

from src.models.github_models import GitHubVoiceoverRequest, GitHubVoiceoverResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def root():
    """主页"""
    with open(os.path.join("static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/video-maker", response_class=HTMLResponse)
async def video_maker_page():
    """视频制作页面"""
    with open(os.path.join("static", "video_maker.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/video-editor3", response_class=HTMLResponse)
async def video_editor3_page():
    """视频文字编辑器页面"""
    with open(os.path.join("static", "video_editor3.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/github-video-maker", response_class=HTMLResponse)
async def github_video_maker_page():
    """GitHub项目视频制作页面"""
    with open(os.path.join("static", "github_video_maker.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/digital-human", response_class=HTMLResponse)
async def digital_human_page():
    """数字人视频生成页面"""
    with open(os.path.join("static", "digital_human.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "message": "服务运行正常"}

@router.get("/api/list-title-fonts")
async def list_title_fonts():
    """主标题字体预设（与 utils.video_utils 中成片主标题一致）。"""
    try:
        from utils.video_utils import title_font_presets_for_api

        return {"success": True, "fonts": title_font_presets_for_api()}
    except Exception as e:
        logger.error(f"列出主标题字体失败: {e}")
        return {"success": False, "message": str(e), "fonts": []}


@router.get("/api/list-music-files")
async def list_music_files():
    """列出 static/music 目录下的所有 MP3 文件"""
    try:
        music_dir = Path("static/music")
        if not music_dir.exists():
            return {"success": False, "message": "音乐目录不存在", "files": []}
        
        # 获取所有 mp3 文件
        mp3_files = list(music_dir.glob("*.mp3"))
        
        files_info = []
        for mp3_file in sorted(mp3_files):
            files_info.append({
                "path": str(mp3_file).replace("\\", "/"),  # 统一使用正斜杠
                "name": mp3_file.stem.replace('_', ' ').title()  # 美化文件名
            })
        
        return {
            "success": True,
            "count": len(files_info),
            "files": files_info
        }
    except Exception as e:
        logger.error(f"列出音乐文件失败：{e}")
        return {"success": False, "message": str(e), "files": []}


@router.get("/api/list-background-images")
async def list_background_images():
    """列出 static/imgs 下默认底图及 static/imgs/backgrounds/ 中的图片，供 GitHub 成片选择。"""
    try:
        exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        files_info = []
        seen = set()

        def add_if_file(rel: str):
            p = Path(rel)
            if not p.is_file():
                return
            key = str(p.resolve())
            if key in seen:
                return
            seen.add(key)
            files_info.append({
                "path": str(p).replace("\\", "/"),
                "name": p.stem.replace("_", " ") or p.name,
            })

        add_if_file("static/imgs/bg.png")

        bg_dir = Path("static/imgs/backgrounds")
        bg_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(bg_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in exts:
                add_if_file(str(f).replace("\\", "/"))

        return {"success": True, "count": len(files_info), "files": files_info}
    except Exception as e:
        logger.error(f"列出背景图失败：{e}")
        return {"success": False, "message": str(e), "files": []}


@router.post("/api/upload-background-image")
async def upload_background_image(image: UploadFile = File(...)):
    """上传成片背景图到 static/imgs/backgrounds/（仅 static/ 下路径可供成片使用）。"""
    try:
        allowed_types = [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
            "image/bmp",
        ]
        if image.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="不支持的图片格式")

        content = await image.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过10MB限制")

        upload_dir = Path("static/imgs/backgrounds")
        upload_dir.mkdir(parents=True, exist_ok=True)

        import uuid

        ext = Path(image.filename or "").suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            ext = ".png"
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = upload_dir / unique_filename

        with open(file_path, "wb") as buffer:
            buffer.write(content)

        rel = str(file_path).replace("\\", "/")
        logger.info(f"背景图上传成功: {image.filename} -> {rel}")

        return {
            "success": True,
            "message": "上传成功",
            "path": rel,
            "filename": unique_filename,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"背景图上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/api/list-subtitle-fonts")
async def list_subtitle_fonts():
    """
    字幕烧录可选字体：系统常见字体 + static/fonts/subtitle 下的自定义 TTF/OTF/TTC。
    将字体文件放入 static/fonts/subtitle/ 后重启服务即可出现在列表中。
    """
    try:
        from utils.subtitle_fonts import subtitle_fonts_for_api

        return subtitle_fonts_for_api()
    except Exception as e:
        logger.error(f"列出字幕字体失败: {e}")
        return {"success": False, "message": str(e), "fonts": [], "fontsdir": ""}


@router.post("/api/render-voiceover", response_model=GitHubVoiceoverResponse)
async def render_voiceover_standalone(request: GitHubVoiceoverRequest):
    """
    主页第五步：为任意基底视频添加 TTS 配音与字幕（与 /api/github/projects/.../voiceover 相同逻辑，不依赖 GitHub 项目）。
    """
    base = request.base_video_path.strip().lstrip("/")
    base_path = Path(base)
    if not base_path.is_file():
        raise HTTPException(status_code=400, detail=f"基底视频不存在: {request.base_video_path}")

    from services.github_voiceover_service import render_voiceover_for_video

    ok, msg, final_url, srt_url = await render_voiceover_for_video(
        base_video_path=base_path,
        script=request.script,
        voice=request.voice or "zh-CN-XiaoxiaoNeural",
        voice_clone_audio_path=request.voice_clone_audio_path,
        mix_bgm=request.mix_bgm,
        bgm_gain_db=request.bgm_gain_db,
        narration_gain_db=request.narration_gain_db,
        burn_subtitles=request.burn_subtitles,
        tts_rate=(request.tts_rate or "+25%").strip(),
        subtitle_fontname=request.subtitle_fontname or "Microsoft YaHei",
        subtitle_fontsize=request.subtitle_fontsize,
        subtitle_margin_bottom_percent=float(request.subtitle_margin_bottom_percent),
        subtitle_max_chars=request.subtitle_max_chars,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=msg or "配音合成失败")
    return GitHubVoiceoverResponse(
        success=True,
        message=msg or "完成",
        final_video_path=final_url,
        srt_path=srt_url,
    )


@router.post("/api/upload-voice-clone-audio")
async def upload_voice_clone_audio(audio: UploadFile = File(...)):
    """上传 IndexTTS 声音克隆参考音频。"""
    try:
        allowed_types = {
            "audio/wav",
            "audio/x-wav",
            "audio/mpeg",
            "audio/mp3",
            "audio/flac",
            "audio/x-flac",
            "audio/ogg",
            "audio/webm",
            "audio/mp4",
            "audio/aac",
            "audio/x-aac",
            "audio/x-m4a",
            "video/mp4",
            "application/octet-stream",
        }
        suffix = Path(audio.filename or "").suffix.lower()
        allowed_suffixes = {".wav", ".mp3", ".flac", ".ogg", ".webm", ".m4a", ".mp4", ".aac"}
        if audio.content_type not in allowed_types and suffix not in allowed_suffixes:
            raise HTTPException(status_code=400, detail="不支持的音频格式，请上传 wav/mp3/flac/ogg/webm/m4a/aac")

        content = await audio.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="音频文件超过50MB限制")
        if not content:
            raise HTTPException(status_code=400, detail="音频文件为空")

        out_dir = Path("data/voice_clones")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_suffix = suffix if suffix in allowed_suffixes else ".wav"
        filename = f"voice_clone_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{safe_suffix}"
        out_path = out_dir / filename
        out_path.write_bytes(content)
        return {
            "success": True,
            "message": "上传成功",
            "path": f"/{out_path.as_posix()}",
            "filename": filename,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"声音克隆音频上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.post("/upload-local-image")
async def upload_local_image(image: UploadFile = File(...)):
    """上传单个本地图片文件"""
    try:
        # 验证文件类型
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp']
        if image.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="不支持的图片格式")
        
        # 验证文件大小（10MB限制）
        content = await image.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="文件大小超过10MB限制")
        
        # 重置文件指针
        await image.seek(0)
        
        # 创建上传目录
        upload_dir = Path("data/local_uploads") / datetime.now().strftime("%Y%m%d")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        import uuid
        file_extension = Path(image.filename).suffix if image.filename else ".jpg"
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # 返回相对路径
        relative_path = str(file_path.relative_to(Path("."))).replace("\\", "/")
        image_path = f"/{relative_path}"
        
        logger.info(f"本地图片上传成功: {image.filename} -> {image_path}")
        
        return {
            "success": True,
            "message": "图片上传成功",
            "image_path": image_path,
            "filename": image.filename,
            "size": len(content)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"本地图片上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.post("/upload-local-video")
async def upload_local_video(video: UploadFile = File(...)):
    """上传单个本地视频文件（与主页本地上传共用目录）"""
    try:
        allowed_types = {
            "video/mp4",
            "video/webm",
            "video/quicktime",
            "video/x-msvideo",
            "video/x-matroska",
        }
        video_exts = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
        ct = (video.content_type or "").split(";")[0].strip().lower()
        ext_ok = Path(video.filename or "").suffix.lower() in video_exts
        if ct not in allowed_types and not (ct in ("", "application/octet-stream") and ext_ok):
            raise HTTPException(
                status_code=400,
                detail="不支持的视频格式，请使用 MP4、WebM、MOV、AVI 或 MKV",
            )

        content = await video.read()
        max_bytes = 200 * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(status_code=400, detail="文件大小超过200MB限制")

        await video.seek(0)

        upload_dir = Path("data/local_uploads") / datetime.now().strftime("%Y%m%d")
        upload_dir.mkdir(parents=True, exist_ok=True)

        import uuid

        ext = Path(video.filename or "").suffix.lower()
        if ext not in {".mp4", ".webm", ".mov", ".avi", ".mkv"}:
            ext = ".mp4"
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = upload_dir / unique_filename

        with open(file_path, "wb") as buffer:
            buffer.write(content)

        relative_path = str(file_path.relative_to(Path("."))).replace("\\", "/")
        video_url_path = f"/{relative_path}"

        logger.info(f"本地视频上传成功: {video.filename} -> {video_url_path}")

        return {
            "success": True,
            "message": "视频上传成功",
            "video_path": video_url_path,
            "image_path": video_url_path,
            "filename": video.filename,
            "size": len(content),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"本地视频上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")