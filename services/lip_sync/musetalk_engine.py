"""MuseTalk 1.5 subprocess wrapper.

MuseTalk requires Python 3.10 + PyTorch 2.0.1 + CUDA 11.8 with a properly
compiled mmcv.  This engine delegates all inference to an isolated conda /
virtualenv Python whose path is resolved as follows (first match wins):

  1. Environment variable  MUSETALK_PYTHON
  2. Auto-detect common conda env locations:
       <conda_base>/envs/musetalk/python.exe   (Windows)
       ~/.conda/envs/musetalk/bin/python        (Linux / macOS)

If none of the above resolve to an executable file the engine is marked
unavailable and a helpful error message is shown.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MUSETALK_ROOT = PROJECT_ROOT / "third_party" / "MuseTalk"
INFERENCE_SCRIPT = MUSETALK_ROOT / "scripts" / "inference.py"

MODELS_DIR = MUSETALK_ROOT / "models"
UNET_V15_PATH = MODELS_DIR / "musetalkV15" / "unet.pth"
UNET_CONFIG_PATH = MODELS_DIR / "musetalkV15" / "musetalk.json"
WHISPER_DIR = MODELS_DIR / "whisper"
VAE_DIR = MODELS_DIR / "sd-vae"
DWPOSE_DIR = MODELS_DIR / "dwpose"
FACE_PARSE_DIR = MODELS_DIR / "face-parse-bisent"

# ---------------------------------------------------------------------------
# Locate the isolated MuseTalk Python interpreter
# ---------------------------------------------------------------------------

def _find_musetalk_python() -> Path | None:
    """Return the path to the isolated MuseTalk Python, or None if not found."""
    # 1. Explicit override via env var
    env_val = os.environ.get("MUSETALK_PYTHON", "").strip()
    if env_val:
        p = Path(env_val)
        if p.is_file():
            return p
        logger.warning("MUSETALK_PYTHON 指向的路径不存在: {}", env_val)

    # 2. Auto-detect common conda env locations (Windows first, then POSIX)
    conda_env_name = os.environ.get("MUSETALK_CONDA_ENV", "musetalk")
    search_bases: list[Path] = []

    for base_candidate in [
        os.environ.get("CONDA_PREFIX", ""),          # active conda env's base sibling
        r"C:\Users\Mingzhu\anaconda3",               # project-specific known path
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

    for base in search_bases:
        for rel in [
            Path("envs") / conda_env_name / "python.exe",   # Windows conda
            Path("envs") / conda_env_name / "bin" / "python",  # Linux/macOS conda
        ]:
            candidate = base / rel
            if candidate.is_file():
                return candidate

    return None


# Cache at module level so repeated calls are cheap
_MUSETALK_PYTHON: Path | None = _find_musetalk_python()


class MuseTalkEngine:
    name = "musetalk"

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def availability_reason(self) -> str | None:
        # Re-detect on every call so that env-var changes take effect without
        # restarting the server.
        global _MUSETALK_PYTHON
        _MUSETALK_PYTHON = _find_musetalk_python()

        if not MUSETALK_ROOT.is_dir():
            return f"未找到 MuseTalk 目录: {MUSETALK_ROOT}"
        if not INFERENCE_SCRIPT.is_file():
            return f"未找到推理脚本: {INFERENCE_SCRIPT}"
        if not UNET_V15_PATH.is_file():
            return f"未找到 MuseTalk v1.5 UNet 模型，请运行 setup_musetalk_env.bat: {UNET_V15_PATH}"
        if not UNET_CONFIG_PATH.is_file():
            return f"未找到 UNet 配置文件: {UNET_CONFIG_PATH}"
        if not (WHISPER_DIR / "config.json").is_file():
            return f"未找到 Whisper 配置文件: {WHISPER_DIR / 'config.json'}"
        if not (WHISPER_DIR / "pytorch_model.bin").is_file():
            return f"未找到 Whisper 模型文件: {WHISPER_DIR / 'pytorch_model.bin'}"
        if not (VAE_DIR / "config.json").is_file():
            return f"未找到 SD-VAE 配置文件: {VAE_DIR / 'config.json'}"
        if not (VAE_DIR / "diffusion_pytorch_model.bin").is_file():
            return f"未找到 SD-VAE 模型文件: {VAE_DIR / 'diffusion_pytorch_model.bin'}"
        if not (DWPOSE_DIR / "dw-ll_ucoco_384.pth").is_file():
            return f"未找到 DWPose 模型文件: {DWPOSE_DIR / 'dw-ll_ucoco_384.pth'}"
        if not (FACE_PARSE_DIR / "79999_iter.pth").is_file():
            return f"未找到 face-parse-bisent 模型文件: {FACE_PARSE_DIR / '79999_iter.pth'}"
        if not (FACE_PARSE_DIR / "resnet18-5c106cde.pth").is_file():
            return f"未找到 face-parse-bisent resnet 文件: {FACE_PARSE_DIR / 'resnet18-5c106cde.pth'}"
        if shutil.which("ffmpeg") is None:
            return "未找到 ffmpeg，可执行文件不在 PATH 中"
        if _MUSETALK_PYTHON is None:
            return (
                "未找到 MuseTalk 独立 Python 环境。\n"
                "请运行 setup_musetalk_env.bat 创建 conda 环境，或者设置环境变量：\n"
                "  MUSETALK_PYTHON=<conda_env_path>\\python.exe\n"
                "例如: set MUSETALK_PYTHON=C:\\Users\\Mingzhu\\anaconda3\\envs\\musetalk\\python.exe"
            )
        return None

    def is_available(self) -> bool:
        return self.availability_reason() is None

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
            raise RuntimeError(f"MuseTalk 不可用: {reason}")

        musetalk_python = _MUSETALK_PYTHON
        assert musetalk_python is not None  # guaranteed by availability_reason()

        avatar_abs = Path(avatar_path).resolve()
        audio_abs = Path(audio_path).resolve()
        output_abs = Path(output_path).resolve()
        output_abs.parent.mkdir(parents=True, exist_ok=True)

        # MuseTalk expects an inference config yaml pointing to video + audio
        # Create a temp yaml for this task
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as cfg_file:
            cfg_path = Path(cfg_file.name)
            # Use forward slashes inside yaml to avoid YAML escape issues on Windows
            video_path_str = avatar_abs.as_posix()
            audio_path_str = audio_abs.as_posix()
            cfg_file.write(
                f"task_0:\n"
                f"  video_path: \"{video_path_str}\"\n"
                f"  audio_path: \"{audio_path_str}\"\n"
                f"  result_name: \"{output_abs.name}\"\n"
            )

        try:
            # Temporary result directory — MuseTalk writes to result_dir/v15/<output_name>
            result_dir = output_abs.parent / f"_musetalk_tmp_{output_abs.stem}"
            result_dir.mkdir(parents=True, exist_ok=True)

            # Use the isolated conda env Python — do NOT inject the main
            # project's PYTHONPATH so that mmcv / mmpose from the conda env
            # are resolved cleanly without any compatibility shims.
            env = os.environ.copy()
            env["PYTHONPATH"] = str(MUSETALK_ROOT)
            # Remove any leftover shim paths from the main env
            env.pop("VIRTUAL_ENV", None)

            logger.info("使用独立 MuseTalk Python: {}", musetalk_python)

            cmd = [
                str(musetalk_python),
                str(INFERENCE_SCRIPT),
                "--unet_model_path", str(UNET_V15_PATH),
                "--unet_config", str(UNET_CONFIG_PATH),
                "--whisper_dir", str(WHISPER_DIR),
                "--inference_config", str(cfg_path),
                "--result_dir", str(result_dir),
                "--version", "v15",
                "--batch_size", str(max(4, min(batch_size * 8, 32))),
                "--use_float16",
            ]

            logger.info("启动 MuseTalk 推理: {}", " ".join(cmd))
            task.update(progress=30, message="正在启动 MuseTalk AI 唇形同步引擎")

            proc = subprocess.Popen(
                cmd,
                cwd=str(MUSETALK_ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )

            task.update(progress=35, message="MuseTalk AI 模型推理中")
            log_lines: list[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                log_lines.append(line)
                logger.info("[MuseTalk] {}", line)

            return_code = proc.wait()
            log_tail = "\n".join(log_lines[-40:])

            if return_code != 0:
                raise RuntimeError(
                    f"MuseTalk 推理失败 (exit={return_code})。末尾日志:\n{log_tail}"
                )

            # MuseTalk writes to result_dir/v15/<output_name>
            generated = result_dir / "v15" / output_abs.name
            if not generated.is_file():
                # Fallback: search for any mp4 in the result dir
                mp4_files = list(result_dir.rglob("*.mp4"))
                mp4_files = [f for f in mp4_files if "_concat" not in f.name]
                if not mp4_files:
                    raise RuntimeError(
                        f"MuseTalk 未生成输出文件，预期路径: {generated}\n末尾日志:\n{log_tail}"
                    )
                generated = mp4_files[0]
                logger.warning("使用备选输出路径: {}", generated)

            shutil.move(str(generated), str(output_abs))
            logger.info("MuseTalk 输出已保存: {}", output_abs)
            task.update(progress=90, message="MuseTalk 推理完成")

        finally:
            # Clean up temp yaml and result dir
            try:
                cfg_path.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                shutil.rmtree(result_dir, ignore_errors=True)
            except Exception:
                pass
