"""Load GIF / animated WebP frames with Pillow for chronicle card heroes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MIN_FRAME_SEC = 0.02
DEFAULT_FRAME_SEC = 0.1
HERO_PLAYBACK_SPEED = 1.5


@dataclass(frozen=True)
class HeroAnimation:
    frames: list[Image.Image]
    durations_sec: list[float]
    animated: bool

    @property
    def cycle_sec(self) -> float:
        total = sum(self.durations_sec)
        return total if total > 0 else DEFAULT_FRAME_SEC


def load_hero_animation(path: str | Path) -> HeroAnimation:
    file_path = Path(path)
    with Image.open(file_path) as src:
        n_frames = int(getattr(src, "n_frames", 1) or 1)
        animated = bool(getattr(src, "is_animated", False)) and n_frames > 1
        if not animated:
            return HeroAnimation(
                frames=[src.convert("RGB").copy()],
                durations_sec=[DEFAULT_FRAME_SEC],
                animated=False,
            )
        canvas = Image.new("RGBA", src.size, (0, 0, 0, 0))
        frames: list[Image.Image] = []
        durations: list[float] = []
        for index in range(n_frames):
            src.seek(index)
            duration = float(src.info.get("duration") or 100) / 1000.0
            layer = src.convert("RGBA")
            canvas = canvas.copy()
            canvas.paste(layer, (0, 0), layer)
            frames.append(canvas.convert("RGB"))
            durations.append(max(MIN_FRAME_SEC, duration if duration > 0 else DEFAULT_FRAME_SEC))
        return HeroAnimation(frames=frames, durations_sec=durations, animated=True)


def hero_frame_at(
    anim: HeroAnimation,
    t: float,
    *,
    speed: float = HERO_PLAYBACK_SPEED,
) -> Image.Image:
    if not anim.frames:
        raise ValueError("hero animation has no frames")
    if not anim.animated or len(anim.frames) == 1:
        return anim.frames[0]
    cycle = anim.cycle_sec
    playback_speed = max(0.01, float(speed))
    elapsed = (float(t) * playback_speed) % cycle
    acc = 0.0
    for frame, duration in zip(anim.frames, anim.durations_sec):
        acc += duration
        if elapsed < acc:
            return frame
    return anim.frames[-1]
