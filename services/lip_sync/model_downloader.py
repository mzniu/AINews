"""Model discovery and download helpers for lip-sync engines."""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WAV2LIP_MODEL_PATH = PROJECT_ROOT / "models" / "wav2lip" / "Wav2Lip_GAN.pth"
DEFAULT_WAV2LIP_URLS: Sequence[str] = (
    os.getenv("WAV2LIP_MODEL_URL", "").strip(),
    "https://hf-mirror.com/Nekochu/Wav2Lip/resolve/main/wav2lip_gan.pth",
)


def candidate_model_paths() -> list[Path]:
    third_party_root = PROJECT_ROOT / "third_party" / "Wav2Lip" / "checkpoints"
    return [
        DEFAULT_WAV2LIP_MODEL_PATH,
        third_party_root / "Wav2Lip_GAN.pth",
        third_party_root / "wav2lip_gan.pth",
    ]


def resolve_existing_model_path() -> Path | None:
    for path in candidate_model_paths():
        if not path.is_file():
            continue
        size_bytes = path.stat().st_size
        min_size = 300 * 1024 * 1024 if "gan" in path.name.lower() else 50 * 1024 * 1024
        if size_bytes >= min_size:
            return path
    return None


def download_wav2lip_model(
    destination: Path = DEFAULT_WAV2LIP_MODEL_PATH,
    urls: Iterable[str] = DEFAULT_WAV2LIP_URLS,
    timeout: int = 300,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return destination

    errors: list[str] = []
    for raw_url in urls:
        url = (raw_url or "").strip()
        if not url:
            continue
        tmp_path = None
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".part", dir=str(destination.parent)) as tmp:
                    tmp_path = Path(tmp.name)
                    shutil.copyfileobj(response, tmp)
            tmp_path.replace(destination)
            return destination
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    raise RuntimeError("无法下载 Wav2Lip 模型，请手动放置到 models/wav2lip/Wav2Lip_GAN.pth。" + (" 详情: " + " | ".join(errors) if errors else ""))