"""Download EchoMimic V2 pretrained weights.

Run via:  setup_echomimic_env.bat  (uses the echomimic conda env)
Or manually: conda run -n echomimic python download_echomimic_models.py

Uses HF mirror (hf-mirror.com) for faster downloads in China.
Falls back to the official HuggingFace endpoint.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure huggingface_hub is installed
# ---------------------------------------------------------------------------
try:
    from huggingface_hub import snapshot_download, hf_hub_download
except ImportError:
    print("[setup] Installing huggingface_hub...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub>=0.23", "-q"])
    from huggingface_hub import snapshot_download, hf_hub_download  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent
ECHOMIMIC_ROOT = PROJECT_ROOT / "third_party" / "echomimic_v2"
WEIGHTS_DIR = ECHOMIMIC_ROOT / "pretrained_weights"

# HF mirror for China users (falls back to HF if not set)
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")

ECHOMIMIC_REPO = "BadToBest/EchoMimicV2"

# Individual large model repos needed by EchoMimic V2
EXTRA_REPOS = {
    "sd-vae-ft-mse": "stabilityai/sd-vae-ft-mse",
    "sd-image-variations-diffusers": "lambdalabs/sd-image-variations-diffusers",
    "wav2vec2-base-960h": "facebook/wav2vec2-base-960h",
}

# Whisper tiny (single file)
WHISPER_TINY_URL = None  # downloaded from EchoMimicV2 repo directly


def _dl(repo_id: str, local_dir: Path, ignore_patterns: list[str] | None = None) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {repo_id} → {local_dir}")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
            endpoint=HF_ENDPOINT,
            ignore_patterns=ignore_patterns or [],
        )
        print(f"  ✓ {repo_id}")
    except Exception as exc:
        print(f"  ✗ {repo_id} failed: {exc}")
        raise


def main() -> None:
    if not ECHOMIMIC_ROOT.is_dir():
        print(f"ERROR: EchoMimic V2 not cloned yet: {ECHOMIMIC_ROOT}")
        print("       Run setup_echomimic_env.bat first.")
        sys.exit(1)

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Model weights directory: {WEIGHTS_DIR}")
    print(f"HuggingFace endpoint: {HF_ENDPOINT}")
    print()

    # 1. Main EchoMimic V2 weights (pth files + audio_processor)
    print("[1/4] Downloading EchoMimicV2 weights (denoising_unet_acc, reference_unet, etc.)...")
    try:
        # Download just the .pth files and audio_processor from EchoMimicV2 repo
        snapshot_download(
            repo_id=ECHOMIMIC_REPO,
            local_dir=str(WEIGHTS_DIR),
            endpoint=HF_ENDPOINT,
            ignore_patterns=["*.bin", "*.safetensors", "*.ot", "flax_model*", "tf_model*"],
        )
        print("  ✓ EchoMimicV2 pth weights")
    except Exception as exc:
        print(f"  ✗ Failed: {exc}")
        print("  Try setting: set HF_ENDPOINT=https://huggingface.co")
        sys.exit(1)

    # 2. sd-vae-ft-mse
    print()
    print("[2/4] Downloading sd-vae-ft-mse...")
    vae_dir = WEIGHTS_DIR / "sd-vae-ft-mse"
    if not (vae_dir / "config.json").is_file():
        _dl(
            repo_id=EXTRA_REPOS["sd-vae-ft-mse"],
            local_dir=vae_dir,
            ignore_patterns=["*.msgpack", "*.h5", "flax*", "tf_*", "rust_model*"],
        )
    else:
        print("  ✓ Already present")

    # 3. sd-image-variations-diffusers (large, ~3.5 GB)
    print()
    print("[3/4] Downloading sd-image-variations-diffusers (large, ~3.5 GB)...")
    svd_dir = WEIGHTS_DIR / "sd-image-variations-diffusers"
    if not (svd_dir / "unet" / "config.json").is_file():
        _dl(
            repo_id=EXTRA_REPOS["sd-image-variations-diffusers"],
            local_dir=svd_dir,
            ignore_patterns=["*.msgpack", "*.h5", "flax*", "tf_*", "*.ot", "rust_model*", "*.safetensors"],
        )
    else:
        print("  ✓ Already present")

    # 4. wav2vec2-base-960h
    print()
    print("[4/4] Downloading wav2vec2-base-960h...")
    w2v_dir = WEIGHTS_DIR / "wav2vec2-base-960h"
    if not (w2v_dir / "config.json").is_file():
        _dl(
            repo_id=EXTRA_REPOS["wav2vec2-base-960h"],
            local_dir=w2v_dir,
            ignore_patterns=["*.msgpack", "*.h5", "flax*", "tf_*", "rust_model*"],
        )
    else:
        print("  ✓ Already present")

    # Summary check
    print()
    print("=" * 60)
    print("Checking required files...")
    required = [
        WEIGHTS_DIR / "denoising_unet_acc.pth",
        WEIGHTS_DIR / "reference_unet.pth",
        WEIGHTS_DIR / "motion_module_acc.pth",
        WEIGHTS_DIR / "pose_encoder.pth",
        WEIGHTS_DIR / "sd-vae-ft-mse" / "config.json",
        WEIGHTS_DIR / "sd-image-variations-diffusers" / "unet" / "config.json",
        WEIGHTS_DIR / "audio_processor" / "tiny.pt",
    ]
    all_ok = True
    for p in required:
        status = "✓" if p.is_file() else "✗ MISSING"
        print(f"  {status}  {p.relative_to(WEIGHTS_DIR)}")
        if not p.is_file():
            all_ok = False

    print()
    if all_ok:
        print("All required weights present. EchoMimic V2 is ready!")
    else:
        print("Some weights are missing. Re-run this script to retry.")
        sys.exit(1)


if __name__ == "__main__":
    main()
