"""EchoMimic V2 subprocess wrapper.

EchoMimic V2 (antgroup) is an audio-driven half-body portrait animation model.
It requires:
  - A reference portrait image (extracted from avatar video)
  - An audio file (WAV)
  - A pose sequence directory (bundled in assets/halfbody_demo/pose/)

The conda env is auto-detected (first match wins):
  1. $ECHOMIMIC_PYTHON env var
  2. <conda_base>/envs/echomimic/python.exe  (Windows)
  3. ~/.conda/envs/echomimic/bin/python       (Linux / macOS)

Setup:
  Run  setup_echomimic_env.bat  to create the environment and download weights.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ECHOMIMIC_ROOT = PROJECT_ROOT / "third_party" / "echomimic_v2"
INFER_SCRIPT = ECHOMIMIC_ROOT / "infer_acc.py"
WEIGHTS_DIR = ECHOMIMIC_ROOT / "pretrained_weights"
POSE_BASE_DIR = ECHOMIMIC_ROOT / "assets" / "halfbody_demo" / "pose"

# Default pose name (natural standing/talking)
DEFAULT_POSE = "01"

# ---------------------------------------------------------------------------
# Locate the isolated EchoMimic Python interpreter
# ---------------------------------------------------------------------------

def _find_echomimic_python() -> Path | None:
    """Return path to the isolated EchoMimic Python, or None if not found."""
    env_val = os.environ.get("ECHOMIMIC_PYTHON", "").strip().strip('"').strip("'")
    if env_val:
        p = Path(env_val)
        if p.is_file():
            return p
        logger.warning("ECHOMIMIC_PYTHON 指向的路径不存在: {}", env_val)

    conda_env_name = os.environ.get("ECHOMIMIC_CONDA_ENV", "echomimic")
    search_bases: list[Path] = []

    for base_candidate in [
        os.environ.get("CONDA_PREFIX", ""),
        r"C:\Users\Mingzhu\anaconda3",
        str(Path.home() / "anaconda3"),
        str(Path.home() / "miniconda3"),
        r"C:\anaconda3",
        r"C:\miniconda3",
        r"C:\ProgramData\Anaconda3",
        r"C:\ProgramData\miniconda3",
        str(Path.home() / ".conda"),
    ]:
        if base_candidate:
            search_bases.append(Path(base_candidate))

    # Search for both "echomimic" and "echomimic_v3" (and any other variant)
    env_names = [conda_env_name, f"{conda_env_name}_v3", f"{conda_env_name}_v2"]

    for base in search_bases:
        for env in env_names:
            for rel in [
                Path("envs") / env / "python.exe",        # Windows conda
                Path("envs") / env / "bin" / "python",    # Linux/macOS
            ]:
                candidate = base / rel
                if candidate.is_file():
                    return candidate

    return None


_ECHOMIMIC_PYTHON: Path | None = _find_echomimic_python()


class EchoMimicV2Engine:
    name = "echomimic"

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def availability_reason(self) -> str | None:
        global _ECHOMIMIC_PYTHON
        _ECHOMIMIC_PYTHON = _find_echomimic_python()

        if not ECHOMIMIC_ROOT.is_dir():
            return f"未找到 EchoMimic V2 目录: {ECHOMIMIC_ROOT}，请运行 setup_echomimic_env.bat"
        if not INFER_SCRIPT.is_file():
            return f"未找到推理脚本: {INFER_SCRIPT}"

        # Essential model weights
        missing = []
        checks = [
            WEIGHTS_DIR / "denoising_unet_acc.pth",
            WEIGHTS_DIR / "reference_unet.pth",
            WEIGHTS_DIR / "motion_module_acc.pth",
            WEIGHTS_DIR / "pose_encoder.pth",
            WEIGHTS_DIR / "sd-vae-ft-mse" / "config.json",
            WEIGHTS_DIR / "sd-image-variations-diffusers" / "unet" / "config.json",
            WEIGHTS_DIR / "audio_processor" / "tiny.pt",
        ]
        for p in checks:
            if not p.is_file():
                missing.append(p.name)
        if missing:
            return f"缺少模型文件: {', '.join(missing)}，请运行 setup_echomimic_env.bat 下载"

        if not POSE_BASE_DIR.is_dir() or not any(POSE_BASE_DIR.iterdir()):
            return f"未找到 pose 序列目录: {POSE_BASE_DIR}"

        if shutil.which("ffmpeg") is None:
            return "未找到 ffmpeg"

        if _ECHOMIMIC_PYTHON is None:
            return (
                "未找到 EchoMimic 独立 Python 环境。\n"
                "请运行 setup_echomimic_env.bat 创建 conda 环境，或者设置环境变量：\n"
                "  ECHOMIMIC_PYTHON=<conda_env_path>\\python.exe"
            )
        return None

    def is_available(self) -> bool:
        return self.availability_reason() is None

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def run(
        self,
        avatar_path: Path,
        audio_path: Path,
        output_path: Path,
        task: Any,
        batch_size: int,
        use_super_resolution: bool,
    ) -> None:
        reason = self.availability_reason()
        if reason:
            raise RuntimeError(f"EchoMimic V2 不可用: {reason}")

        echomimic_python = _ECHOMIMIC_PYTHON
        assert echomimic_python is not None

        avatar_abs = Path(avatar_path).resolve()
        audio_abs = Path(audio_path).resolve()
        output_abs = Path(output_path).resolve()
        output_abs.parent.mkdir(parents=True, exist_ok=True)

        # Temp reference image extracted from avatar video — use short name to avoid MAX_PATH
        import uuid as _uuid
        ref_image_path = output_abs.parent / f"_em_{_uuid.uuid4().hex[:8]}.png"
        pose_tmp_dir: Path | None = None
        cfg_path: Path | None = None

        _IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        try:
            # 1. Get reference frame: copy directly if image, otherwise extract from video
            if avatar_abs.suffix.lower() in _IMG_EXTS:
                task.update(progress=20, message="正在使用上传图片作为参考画面")
                shutil.copy2(avatar_abs, ref_image_path)
            else:
                task.update(progress=20, message="正在从形象视频提取参考画面")
                self._extract_reference_frame(avatar_abs, ref_image_path)

            # 2. Get audio duration and prepare looped pose
            task.update(progress=22, message="正在准备动作姿态序列")
            audio_duration = self._get_audio_duration(audio_abs)
            fps = 24
            needed_frames = int(audio_duration * fps) + fps  # slight buffer

            pose_name = os.environ.get("ECHOMIMIC_POSE", DEFAULT_POSE)
            pose_src = POSE_BASE_DIR / pose_name
            if not pose_src.is_dir():
                available = [d for d in POSE_BASE_DIR.iterdir() if d.is_dir()]
                if not available:
                    raise RuntimeError(f"未找到任何 pose 序列: {POSE_BASE_DIR}")
                pose_src = sorted(available)[0]
                logger.warning("pose '{}' 不存在，使用 '{}'", pose_name, pose_src.name)

            pose_dir, pose_tmp_dir = self._prepare_looped_pose_dir(pose_src, needed_frames)

            # 3. Write temp YAML config
            cfg_path = self._write_infer_config(ref_image_path, audio_abs, pose_dir)

            # 4. Build command
            # Pose .npy files are pre-computed at 768x768; must match to avoid shape mismatch
            width = int(os.environ.get("ECHOMIMIC_W", "768"))
            height = int(os.environ.get("ECHOMIMIC_H", "768"))
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ECHOMIMIC_ROOT)
            env.pop("VIRTUAL_ENV", None)
            # triton-windows 3.6.0 breaks xformers 0.0.28 at import time (JITCallable API change).
            # Disable xformers' triton-based splitk kernel; falls back to standard flash-attn.
            env["XFORMERS_FORCE_DISABLE_TRITON"] = "1"
            ffmpeg_exe = shutil.which("ffmpeg")
            if ffmpeg_exe:
                env["FFMPEG_PATH"] = str(Path(ffmpeg_exe).parent)

            steps = int(os.environ.get("ECHOMIMIC_STEPS", "20"))
            cfg_scale = float(os.environ.get("ECHOMIMIC_CFG", "2.5"))
            cmd = [
                str(echomimic_python),
                str(INFER_SCRIPT),
                "--config", str(cfg_path),
                "-W", str(width),
                "-H", str(height),
                "-L", str(min(needed_frames, 99999)),
                "--steps", str(steps),
                "--cfg", str(cfg_scale),
                "--seed", "42",
                "--fps", str(fps),
                "--device", "cuda",
            ]

            logger.info("使用独立 EchoMimic Python: {}", echomimic_python)
            logger.info("启动 EchoMimic V2 推理: {}", " ".join(cmd))
            logger.info("参考图像: {}  音频时长: {:.1f}s  帧数: {}  pose: {}",
                        ref_image_path, audio_duration, needed_frames, pose_src.name)
            task.update(progress=30, message=f"EchoMimic V2 扩散模型推理中（steps={steps}, cfg={cfg_scale}，约{int(audio_duration/60)*3+3}分钟，请耐心等待）")

            proc = subprocess.Popen(
                cmd,
                cwd=str(ECHOMIMIC_ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )

            log_lines: list[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                log_lines.append(line)
                logger.info("[EchoMimic] {}", line)

            return_code = proc.wait()
            log_tail = "\n".join(log_lines[-50:])

            if return_code != 0:
                raise RuntimeError(
                    f"EchoMimic V2 推理失败 (exit={return_code})。末尾日志:\n{log_tail}"
                )

            # 5. Find most recently created _sig.mp4 in output/
            output_base = ECHOMIMIC_ROOT / "output"
            mp4_files = sorted(
                output_base.rglob("*_sig.mp4"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not mp4_files:
                raise RuntimeError(
                    f"EchoMimic V2 未生成输出文件，预期在 {output_base}\n末尾日志:\n{log_tail}"
                )

            generated = mp4_files[0]
            shutil.move(str(generated), str(output_abs))
            logger.info("EchoMimic V2 输出已保存: {}", output_abs)
            task.update(progress=90, message="EchoMimic V2 推理完成")

        finally:
            for p in [ref_image_path, cfg_path]:
                if p is not None:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except Exception:
                        pass
            if pose_tmp_dir is not None:
                try:
                    shutil.rmtree(pose_tmp_dir, ignore_errors=True)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_reference_frame(self, video_path: Path, out_image: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg
        cmd = [
            ffmpeg, "-y",
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(out_image),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not out_image.is_file():
            raise RuntimeError(f"帧提取失败: {result.stderr[-500:]}")
        logger.info("参考图像已提取: {}", out_image)

    def _get_audio_duration(self, audio_path: Path) -> float:
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            result = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data["format"]["duration"])
        # fallback
        return 60.0

    def _prepare_looped_pose_dir(self, pose_src: Path, needed_frames: int) -> tuple[Path, Path | None]:
        """Return (pose_dir_to_use, tmp_dir_or_None).

        If the source has enough frames, return the source directly.
        Otherwise, create a temp dir with looped npy files.
        """
        src_files = sorted(
            [p for p in pose_src.glob("*.npy") if p.stem.isdigit()],
            key=lambda p: int(p.stem),
        )
        if not src_files:
            raise RuntimeError(f"pose 目录中没有 npy 文件: {pose_src}")

        n_src = len(src_files)
        if n_src >= needed_frames:
            return pose_src, None  # no looping needed

        logger.info("循环 pose 序列: {} 帧 → {} 帧 (pose={})", n_src, needed_frames, pose_src.name)
        tmp_dir = Path(tempfile.mkdtemp(prefix="echomimic_pose_"))
        for i in range(needed_frames):
            src = src_files[i % n_src]
            dst = tmp_dir / f"{i}.npy"
            shutil.copy2(src, dst)
        return tmp_dir, tmp_dir

    def _write_infer_config(self, ref_image: Path, audio: Path, pose_dir: Path) -> Path:
        """Write a temp infer_acc YAML config and return its path."""
        ref_posix = ref_image.as_posix()
        audio_posix = audio.as_posix()
        # pose_dir must end with "/" so infer_acc.py treats it as a directory
        pose_posix = str(pose_dir).replace("\\", "/").rstrip("/") + "/"

        yaml_content = f"""pretrained_base_model_path: "./pretrained_weights/sd-image-variations-diffusers"
pretrained_vae_path: "./pretrained_weights/sd-vae-ft-mse"

denoising_unet_path: "./pretrained_weights/denoising_unet_acc.pth"
reference_unet_path: "./pretrained_weights/reference_unet.pth"
pose_encoder_path: "./pretrained_weights/pose_encoder.pth"
motion_module_path: "./pretrained_weights/motion_module_acc.pth"

audio_mapper_path: "./pretrained_weights/audio_mapper-50000.pth"
auido_guider_path: "./pretrained_weights/wav2vec2-base-960h"
auto_flow_path: "./pretrained_weights/AutoFlow"
audio_model_path: "./pretrained_weights/audio_processor/tiny.pt"
inference_config: "./configs/inference/inference_v2.yaml"
weight_dtype: "fp16"

test_cases:
  "{ref_posix}":
    - "{audio_posix}"
    - "{pose_posix}"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
            encoding="utf-8", dir=str(ECHOMIMIC_ROOT),
        ) as f:
            f.write(yaml_content)
            return Path(f.name)
