"""Attach generated cover image as a short intro clip on rendered videos."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger
from PIL import Image

from src.utils.config import Config

DEFAULT_INTRO_DURATION_SEC = 1.0


def letterbox_image_on_canvas(
    image: Image.Image,
    canvas_w: int,
    canvas_h: int,
    *,
    bg_color: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0:
        return canvas
    scale = min(canvas_w / src_w, canvas_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x = (canvas_w - new_w) // 2
    y = (canvas_h - new_h) // 2
    canvas.paste(resized, (x, y))
    return canvas


def _resolve_media_path(raw: str) -> Path:
    cleaned = str(raw or "").strip().lstrip("/").replace("\\", "/")
    return (Config.ROOT_DIR / cleaned).resolve()


def prepend_cover_intro_to_video(
    *,
    video_path: str,
    cover_path: str,
    intro_duration: float = DEFAULT_INTRO_DURATION_SEC,
) -> dict[str, object]:
    """Prepend a static cover frame as the first second of the video."""
    video_file = _resolve_media_path(video_path)
    cover_file = _resolve_media_path(cover_path)
    if not video_file.is_file():
        return {"success": False, "error": f"video_missing: {video_path}"}
    if not cover_file.is_file():
        return {"success": False, "error": f"cover_missing: {cover_path}"}
    if intro_duration <= 0:
        return {"success": False, "error": "invalid_intro_duration"}

    from moviepy import ImageClip, VideoFileClip, concatenate_videoclips

    temp_output = video_file.with_suffix(".cover_intro.tmp.mp4")
    video = VideoFileClip(str(video_file))
    fps = float(video.fps or 24)
    width, height = video.size

    with Image.open(cover_file) as cover_image:
        frame = letterbox_image_on_canvas(cover_image.convert("RGB"), width, height)
    intro = ImageClip(np.asarray(frame, dtype=np.uint8)).with_duration(intro_duration).with_fps(fps)

    if video.audio is not None:
        delayed_audio = video.audio.with_start(intro_duration)
        body = video.without_audio()
        final = concatenate_videoclips([intro, body], method="compose").with_audio(delayed_audio)
    else:
        final = concatenate_videoclips([intro, video], method="compose")

    try:
        final.write_videofile(
            str(temp_output),
            fps=fps,
            codec="libx264",
            audio_codec="aac" if video.audio is not None else None,
            temp_audiofile="temp-audio.m4a" if video.audio is not None else None,
            remove_temp=True,
            logger=None,
        )
        temp_output.replace(video_file)
    finally:
        for clip in (intro, video, final):
            try:
                clip.close()
            except Exception:
                pass

    rel = f"/{video_file.relative_to(Config.ROOT_DIR).as_posix()}"
    logger.info(f"Prepended cover intro to video: {rel} ({intro_duration}s)")
    return {
        "success": True,
        "video_path": rel,
        "intro_duration": intro_duration,
        "cover_path": cover_path,
    }
