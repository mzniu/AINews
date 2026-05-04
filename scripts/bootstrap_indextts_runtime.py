"""Copy an IndexTTS runtime into AINews-managed data/ storage.

The runtime is intentionally kept under data/indextts_runtime/tts-2 because it
contains a bundled Python environment and model checkpoints. The repository's
.gitignore excludes data/, so these heavy assets stay local.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_ROOT / "data" / "indextts_runtime" / "tts-2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap local IndexTTS runtime for AINews")
    parser.add_argument("--source", required=True, help="Existing tts-2 project directory")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="Target runtime directory")
    parser.add_argument("--overwrite", action="store_true", help="Remove target before copying")
    return parser.parse_args()


def validate_runtime(path: Path) -> None:
    required = [
        path / "py312" / "python.exe",
        path / "checkpoints" / "config.yaml",
        path / "kelong_tts2.cp310-win_amd64.pyd",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("IndexTTS runtime is incomplete: " + "; ".join(missing))


def ignore_runtime_noise(dir_path: str, names: list[str]) -> set[str]:
    noisy_dirs = {"outputs", "tmp", "__pycache__", ".git"}
    noisy_suffixes = {".log", ".tmp"}
    ignored: set[str] = set()
    for name in names:
        p = Path(dir_path) / name
        if name in noisy_dirs:
            ignored.add(name)
        elif p.is_file() and p.suffix.lower() in noisy_suffixes:
            ignored.add(name)
    return ignored


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    target = Path(args.target).expanduser()
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target = target.resolve()

    if not source.is_dir():
        raise FileNotFoundError(f"Source runtime does not exist: {source}")
    validate_runtime(source)

    if target.exists() and args.overwrite:
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore_runtime_noise)
    validate_runtime(target)

    print(f"IndexTTS runtime ready: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())