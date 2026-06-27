"""End-to-end MuseTalk inference test using test wav/avatar files."""
import sys
import subprocess
import tempfile
import os
from pathlib import Path

MUSETALK_PYTHON = Path(r"C:\Users\Mingzhu\anaconda3\envs\musetalk\python.exe")
MUSETALK_ROOT = Path(r"D:\git\AINews\AINews\third_party\MuseTalk")
INFERENCE_SCRIPT = MUSETALK_ROOT / "scripts" / "inference.py"
MODELS_DIR = MUSETALK_ROOT / "models"

AVATAR = Path(r"D:\git\AINews\AINews\data\digital_human\avatars\wav2lip_test_short.mp4")
AUDIO  = Path(r"D:\git\AINews\AINews\data\digital_human\audio\wav2lip_test_short.wav")
OUTPUT = Path(r"D:\git\AINews\AINews\data\digital_human\outputs\musetalk_e2e_test.mp4")

# Write inference config yaml
with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
    cfg_path = Path(f.name)
    f.write(
        f'task_0:\n'
        f'  video_path: "{AVATAR.as_posix()}"\n'
        f'  audio_path: "{AUDIO.as_posix()}"\n'
        f'  result_name: "{OUTPUT.name}"\n'
    )

result_dir = OUTPUT.parent / "_musetalk_tmp_e2e_test"
result_dir.mkdir(parents=True, exist_ok=True)

env = os.environ.copy()
env["PYTHONPATH"] = str(MUSETALK_ROOT)
env.pop("VIRTUAL_ENV", None)

cmd = [
    str(MUSETALK_PYTHON),
    str(INFERENCE_SCRIPT),
    "--unet_model_path", str(MODELS_DIR / "musetalkV15" / "unet.pth"),
    "--unet_config",     str(MODELS_DIR / "musetalkV15" / "musetalk.json"),
    "--whisper_dir",     str(MODELS_DIR / "whisper"),
    "--inference_config", str(cfg_path),
    "--result_dir",      str(result_dir),
    "--version",         "v15",
    "--batch_size",      "8",
    "--use_float16",
]

print("Running:", " ".join(cmd))
print()

proc = subprocess.run(cmd, cwd=str(MUSETALK_ROOT), env=env)
print()
print(f"Return code: {proc.returncode}")

if proc.returncode == 0:
    # Find output in result_dir
    candidates = list(result_dir.rglob("*.mp4"))
    if candidates:
        out = candidates[0]
        import shutil
        shutil.copy(out, OUTPUT)
        print(f"SUCCESS: output saved to {OUTPUT}")
    else:
        print("WARNING: process succeeded but no .mp4 found in result_dir")
else:
    print("FAILED")
    sys.exit(1)
