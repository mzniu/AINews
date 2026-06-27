"""Digital human video generation service.

The first implementation keeps the API contract compatible with the
MetaHuman4-style workflow: avatar video + audio + generation options -> task ->
progress -> output video.  When no external lip-sync engine is configured, it
creates a usable talking-head placeholder by looping/cutting the uploaded avatar
video and replacing its audio track.
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException, UploadFile
from loguru import logger

from services.lip_sync import lip_sync_engine_manager


PROJECT_ROOT = Path.cwd()
DIGITAL_HUMAN_DIR = Path("data/digital_human")
AVATAR_DIR = DIGITAL_HUMAN_DIR / "avatars"
AUDIO_DIR = DIGITAL_HUMAN_DIR / "audio"
OUTPUT_DIR = DIGITAL_HUMAN_DIR / "outputs"
KNOWN_METAHUMAN_REFERENCE_DIR = Path(
    r"D:\BaiduNetdiskDownload\MetaHuman-2\MetaHuman4_V2\MetaHuman4_V2\_internal\app3_server\_internal\免训练数字人模型"
)

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".wmv", ".flv"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _safe_filename(filename: str, fallback_suffix: str) -> str:
    raw = Path(filename or "").name.strip()
    suffix = Path(raw).suffix.lower() or fallback_suffix
    stem = Path(raw).stem or "upload"
    stem = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", stem).strip("._") or "upload"
    return f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"


def _public_url(path: Path) -> str:
    return "/" + str(path.as_posix()).lstrip("/")


def _resolve_project_path(value: str) -> Path:
    if not value or not value.strip():
        raise ValueError("路径不能为空")

    raw = value.strip().replace("\\", "/")
    if raw.startswith("/data/") or raw.startswith("/static/"):
        raw = raw.lstrip("/")

    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    allowed = [root / "data", root / "static", *_reference_roots()]
    if not any(base in resolved.parents or resolved == base for base in allowed):
        raise ValueError("仅允许使用项目 data/static 目录下的文件")
    if not resolved.is_file():
        raise FileNotFoundError(f"文件不存在: {value}")
    return resolved


def _reference_roots() -> List[Path]:
    roots: List[Path] = []
    reference_dir = os.getenv("METAHUMAN_REFERENCE_DIR", "").strip()
    if reference_dir:
        roots.append(Path(reference_dir).expanduser().resolve())
    if KNOWN_METAHUMAN_REFERENCE_DIR.is_dir():
        roots.append(KNOWN_METAHUMAN_REFERENCE_DIR.resolve())
    return roots


def _duration_seconds(media_path: Path) -> float:
    try:
        from moviepy import AudioFileClip, VideoFileClip

        clip_cls = AudioFileClip if media_path.suffix.lower() in AUDIO_SUFFIXES else VideoFileClip
        clip = clip_cls(str(media_path))
        try:
            return float(clip.duration or 0)
        finally:
            clip.close()
    except Exception as exc:
        logger.warning(f"读取媒体时长失败: {media_path}, {exc}")
        return 0.0


@dataclass
class DigitalHumanTask:
    task_id: str
    status: str = "pending"
    progress: int = 0
    message: str = "等待开始"
    output_url: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def as_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "output_url": self.output_url,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()


class DigitalHumanService:
    def __init__(self) -> None:
        self.tasks: Dict[str, DigitalHumanTask] = {}
        self._lock = asyncio.Lock()
        for directory in (AVATAR_DIR, AUDIO_DIR, OUTPUT_DIR):
            directory.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload: UploadFile, kind: str) -> Dict:
        suffix = Path(upload.filename or "").suffix.lower()
        if kind == "avatar":
            if suffix not in VIDEO_SUFFIXES and suffix not in IMAGE_SUFFIXES:
                raise HTTPException(status_code=400, detail="请上传视频（mp4/mov/webm 等）或图片（jpg/png/webp 等）")
            target_dir = AVATAR_DIR
            fallback_suffix = ".mp4" if suffix in VIDEO_SUFFIXES else ".jpg"
            limit = 500 * 1024 * 1024
        elif kind == "audio":
            if suffix not in AUDIO_SUFFIXES:
                raise HTTPException(status_code=400, detail="请上传 mp3/wav/m4a/aac/ogg/flac 等音频文件")
            target_dir = AUDIO_DIR
            fallback_suffix = ".mp3"
            limit = 200 * 1024 * 1024
        else:
            raise HTTPException(status_code=400, detail="未知上传类型")

        filename = _safe_filename(upload.filename or "upload", fallback_suffix)
        target = target_dir / filename
        total = 0
        with open(target, "wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail="文件超过大小限制")
                output.write(chunk)

        logger.info(f"数字人{kind}上传完成: {upload.filename} -> {target}")
        return {
            "filename": filename,
            "path": str(target).replace("\\", "/"),
            "url": _public_url(target),
            "size_bytes": total,
            "duration": round(_duration_seconds(target), 2),
        }

    def list_avatars(self) -> List[Dict]:
        avatars: List[Dict] = []
        for path in sorted(AVATAR_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.is_file() and path.suffix.lower() in (VIDEO_SUFFIXES | IMAGE_SUFFIXES):
                is_video = path.suffix.lower() in VIDEO_SUFFIXES
                avatars.append({
                    "name": path.name,
                    "label": path.stem,
                    "path": str(path).replace("\\", "/"),
                    "url": _public_url(path),
                    "source": "uploaded",
                    "media_type": "video" if is_video else "image",
                    "size_bytes": path.stat().st_size,
                    "duration": round(_duration_seconds(path), 2) if is_video else 0,
                })

        for reference_root in _reference_roots():
            for item in sorted(reference_root.iterdir()):
                info_file = item / "info.json"
                if not item.is_dir() or not info_file.is_file():
                    continue
                video_files = [p for p in item.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES]
                if not video_files:
                    continue
                cover = item / "cover.jpg"
                avatars.append({
                    "name": item.name,
                    "label": item.name,
                    "path": str(video_files[0]).replace("\\", "/"),
                    "url": None,
                    "cover": str(cover) if cover.is_file() else None,
                    "source": "metahuman-reference",
                    "duration": round(_duration_seconds(video_files[0]), 2),
                })
        return avatars

    def list_audio(self) -> List[Dict]:
        audio_files: List[Dict] = []
        for path in sorted(AUDIO_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES:
                audio_files.append({
                    "name": path.name,
                    "label": path.stem,
                    "url": _public_url(path),
                    "size_bytes": path.stat().st_size,
                    "duration": round(_duration_seconds(path), 2),
                })
        return audio_files

    async def create_task(
        self,
        avatar_video: str,
        audio_file: str,
        mode: str = "fast",
        engine: str = "auto",
        use_super_resolution: bool = False,
        use_action_generalization: bool = False,
        batch_size: int = 4,
    ) -> Dict:
        avatar_path = _resolve_project_path(avatar_video)
        audio_path = _resolve_project_path(audio_file)
        mode = (mode or "fast").strip().lower()
        if mode not in {"fast", "ai"}:
            raise ValueError("mode 仅支持 fast 或 ai")
        engine = (engine or "auto").strip().lower()
        if engine not in {"auto", "echomimic", "musetalk", "wav2lip"}:
            raise ValueError("engine 仅支持 auto、echomimic、musetalk 或 wav2lip")
        task_id = uuid.uuid4().hex
        task = DigitalHumanTask(task_id=task_id)
        async with self._lock:
            self.tasks[task_id] = task

        asyncio.create_task(self._run_task(
            task,
            avatar_path=avatar_path,
            audio_path=audio_path,
            mode=mode,
            engine=engine,
            use_super_resolution=bool(use_super_resolution),
            use_action_generalization=bool(use_action_generalization),
            batch_size=max(1, min(int(batch_size or 4), 32)),
        ))
        return task.as_dict()

    def get_task(self, task_id: str) -> Dict:
        task = self.tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task.as_dict()

    async def _run_task(
        self,
        task: DigitalHumanTask,
        avatar_path: Path,
        audio_path: Path,
        mode: str,
        engine: str,
        use_super_resolution: bool,
        use_action_generalization: bool,
        batch_size: int,
    ) -> None:
        try:
            task.update(status="running", progress=5, message="正在准备素材")
            await asyncio.to_thread(
                self._compose_locally,
                task,
                avatar_path,
                audio_path,
                mode,
                engine,
                use_super_resolution,
                use_action_generalization,
                batch_size,
            )
        except Exception as exc:
            logger.exception(f"数字人视频生成失败 task_id={task.task_id}")
            task.update(status="failed", progress=100, message="生成失败", error=str(exc))

    def _compose_locally(
        self,
        task: DigitalHumanTask,
        avatar_path: Path,
        audio_path: Path,
        mode: str,
        engine: str,
        use_super_resolution: bool,
        use_action_generalization: bool,
        batch_size: int,
    ) -> None:
        task.update(progress=15, message="正在分析音频和形象视频")
        output_path = OUTPUT_DIR / f"digital_human_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task.task_id[:8]}.mp4"
        selected_engine = "fast"

        if mode == "ai":
            selected_engine = self._compose_with_lipsync(
                avatar_path=avatar_path,
                audio_path=audio_path,
                output_path=output_path,
                task=task,
                batch_size=batch_size,
                engine=engine,
                use_super_resolution=use_super_resolution,
            )
        else:
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                self._compose_with_ffmpeg(ffmpeg, avatar_path, audio_path, output_path, task)
            else:
                self._compose_with_moviepy(avatar_path, audio_path, output_path, task)

        logger.info(
            "数字人视频生成完成: output={} mode={} super_resolution={} action_generalization={} batch_size={}",
            output_path,
            mode,
            use_super_resolution,
            use_action_generalization,
            batch_size,
        )
        task.update(
            status="done",
            progress=100,
            message=(f"生成完成（AI 唇形同步 / {selected_engine}）" if mode == "ai" else "生成完成（本地音画合成模式）"),
            output_url=_public_url(output_path),
        )

    def _compose_with_lipsync(
        self,
        avatar_path: Path,
        audio_path: Path,
        output_path: Path,
        task: DigitalHumanTask,
        batch_size: int,
        engine: str,
        use_super_resolution: bool,
    ) -> str:
        return lip_sync_engine_manager.run_ai(
            avatar_path=avatar_path,
            audio_path=audio_path,
            output_path=output_path,
            task=task,
            batch_size=batch_size,
            engine_preference=engine,
            use_super_resolution=use_super_resolution,
        )

    def _compose_with_ffmpeg(
        self,
        ffmpeg: str,
        avatar_path: Path,
        audio_path: Path,
        output_path: Path,
        task: DigitalHumanTask,
    ) -> None:
        import threading

        task.update(progress=35, message="正在调用 ffmpeg 合成视频")
        audio_duration = _duration_seconds(audio_path)
        cmd = [
            ffmpeg,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(avatar_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            str(output_path),
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        # Drain stderr in a background thread to prevent pipe buffer deadlock
        stderr_lines: List[str] = []

        def _drain_stderr() -> None:
            for line in proc.stderr:  # type: ignore[union-attr]
                stderr_lines.append(line.rstrip())

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        out_time_ms = int(line.split("=", 1)[1])
                        if audio_duration > 0:
                            pct = min(88, 35 + int(53 * (out_time_ms / 1_000_000) / audio_duration))
                            task.update(progress=pct, message="正在调用 ffmpeg 合成视频")
                    except ValueError:
                        pass
            proc.wait()
            stderr_thread.join(timeout=5.0)
        except Exception:
            proc.kill()
            proc.wait()
            stderr_thread.join(timeout=2.0)
            raise
        if proc.returncode != 0:
            raise RuntimeError("\n".join(stderr_lines[-30:]) or "ffmpeg 合成失败")
        task.update(progress=90, message="正在整理输出文件")

    def _compose_with_moviepy(
        self,
        avatar_path: Path,
        audio_path: Path,
        output_path: Path,
        task: DigitalHumanTask,
    ) -> None:
        task.update(progress=35, message="正在使用 MoviePy 合成视频")
        from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips

        video = VideoFileClip(str(avatar_path))
        audio = AudioFileClip(str(audio_path))
        final_clip = None
        clips = []
        try:
            audio_duration = float(audio.duration or video.duration or 1)
            if video.duration and video.duration < audio_duration:
                loop_count = max(1, math.ceil(audio_duration / video.duration))
                clips = [video.copy() for _ in range(loop_count)]
                final_clip = concatenate_videoclips(clips).subclipped(0, audio_duration)
            else:
                final_clip = video.subclipped(0, min(video.duration, audio_duration))
            final_clip = final_clip.with_audio(audio.subclipped(0, final_clip.duration))
            task.update(progress=70, message="正在写入视频文件")
            final_clip.write_videofile(
                str(output_path),
                fps=24,
                codec="libx264",
                audio_codec="aac",
                logger=None,
            )
        finally:
            if final_clip is not None:
                final_clip.close()
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass
            audio.close()
            video.close()


digital_human_service = DigitalHumanService()