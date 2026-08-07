"""Pick a random background music file for video rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

DEFAULT_BGM = "static/music/background.mp3"


def pick_random_bgm(
    music_dir: str | Path,
    *,
    rng: Callable[[Sequence[str]], str] | None = None,
) -> str:
    root = Path(music_dir)
    if root.is_dir():
        files = sorted(p.as_posix() for p in root.glob("*.mp3") if p.is_file())
        if files:
            if rng:
                return rng(files)
            import random

            return random.choice(files)
    return DEFAULT_BGM
