"""Attach generated cover image as a short intro clip on rendered videos."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger
from PIL import Image

from src.utils.config import Config

DEFAULT_INTRO_DURATION_SEC = 1.0 / 24


def _audio_sample_fps(audio) -> int:
    fps = int(getattr(audio, "fps", None) or 44100)
    return 44100 if fps < 1000 else fps


def _normalize_sample_block(block: np.ndarray, nchannels: int) -> np.ndarray | None:
    arr = np.asarray(block, dtype=np.float32)
    if arr.ndim == 1:
        if arr.size == nchannels:
            return arr.reshape(1, nchannels)
        if nchannels == 1:
            return arr.reshape(-1, 1)
        return None
    if arr.ndim == 2:
        if arr.shape[1] == nchannels:
            return arr
        if arr.shape[1] == 1 and nchannels > 1:
            return np.repeat(arr, nchannels, axis=1)
        if arr.shape[0] == nchannels and arr.shape[1] != nchannels:
            return arr.T
    return None


def _audio_to_samples(audio, fps: int) -> np.ndarray:
    nchannels = int(getattr(audio, "nchannels", 2) or 2)
    try:
        blocks = []
        for chunk in audio.iter_chunks(fps=fps, chunksize=max(fps, 4000), quantize=False):
            normalized = _normalize_sample_block(chunk, nchannels)
            if normalized is None or normalized.shape[0] < 2:
                raise ValueError("audio chunk is not a sample stream")
            blocks.append(normalized)
        if blocks:
            return np.vstack(blocks)
    except Exception:
        pass
    duration = float(audio.duration or 0)
    n = max(1, int(round(duration * fps)))
    rows = []
    for index in range(n):
        frame = np.atleast_1d(audio.get_frame(index / float(fps))).astype(np.float32)
        if frame.size == 1 and nchannels > 1:
            frame = np.repeat(frame, nchannels)
        elif frame.size != nchannels:
            padded = np.zeros(nchannels, dtype=np.float32)
            padded[: min(nchannels, frame.size)] = frame.reshape(-1)[:nchannels]
            frame = padded
        rows.append(frame.reshape(nchannels))
    return np.vstack(rows)


def _trim_trailing_silence(samples: np.ndarray) -> np.ndarray:
    if samples.shape[0] < 2048:
        return samples
    rms = np.sqrt(np.mean(np.square(samples), axis=1))
    peak = float(np.max(rms))
    if peak <= 0:
        return samples
    threshold = max(0.008, 0.02 * peak)
    nonzero = np.flatnonzero(rms > threshold)
    if nonzero.size == 0:
        return samples
    end = int(nonzero[-1]) + 1
    min_keep = max(int(0.5 * samples.shape[0]), 1)
    return samples[: max(end, min_keep)]


def fit_audio_to_duration(audio, duration: float, *, speed: float = 1.0):
    """Build a PCM audio clip that lasts exactly ``duration`` seconds.

    Loops source samples if needed so BGM covers the full video, including
    extra cover-intro time. Optional ``speed`` skips through the source
    (1.1 keeps the existing flash-news BGM pacing).
    """
    from moviepy.audio.AudioClip import AudioArrayClip

    fps = _audio_sample_fps(audio)
    samples = _audio_to_samples(audio, fps)
    if samples.ndim == 1:
        samples = samples.reshape(-1, 1)
    samples = _trim_trailing_silence(samples)
    need = max(1, int(round(float(duration) * fps)))
    nchannels = samples.shape[1]
    if samples.shape[0] == 0:
        return AudioArrayClip(np.zeros((need, nchannels), dtype=np.float32), fps=fps)
    speed = float(speed) if speed and speed > 0 else 1.0
    idx = (np.arange(need) * speed).astype(np.int64) % samples.shape[0]
    return AudioArrayClip(samples[idx], fps=fps)


def shift_audio_for_cover_intro(audio, intro_duration: float):
    """Extend BGM so it covers the original video plus the cover intro."""
    total = float(audio.duration or 0) + float(intro_duration)
    return fit_audio_to_duration(audio, total)


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
    """Prepend a static cover frame (default: 1 frame) at the start of the video."""
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
        extended_audio = fit_audio_to_duration(
            video.audio, float(video.duration) + float(intro_duration)
        )
        body = video.without_audio()
        final = concatenate_videoclips([intro, body], method="compose").with_audio(extended_audio)
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
