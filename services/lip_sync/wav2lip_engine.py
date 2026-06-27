"""Wav2Lip subprocess wrapper."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from services.lip_sync.model_downloader import resolve_existing_model_path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WAV2LIP_ROOT = PROJECT_ROOT / "third_party" / "Wav2Lip"
INFERENCE_SCRIPT = WAV2LIP_ROOT / "inference.py"


class Wav2LipEngine:
    name = "wav2lip"

    def _validate_checkpoint(self, model_path: Path) -> None:
        import torch

        try:
            checkpoint = torch.load(str(model_path), map_location="cpu")
        except Exception as exc:
            raise RuntimeError(f"Wav2Lip 模型权重不可用或未下载完整: {model_path} ({exc})") from exc
        if not isinstance(checkpoint, dict):
            raise RuntimeError(f"Wav2Lip 模型权重格式异常: {model_path}")

    def availability_reason(self) -> str | None:
        if not WAV2LIP_ROOT.is_dir():
            return f"未找到 Wav2Lip 目录: {WAV2LIP_ROOT}"
        if not INFERENCE_SCRIPT.is_file():
            return f"未找到推理脚本: {INFERENCE_SCRIPT}"
        model_path = resolve_existing_model_path()
        if model_path is None:
            return "未找到模型权重，请放置到 models/wav2lip/Wav2Lip_GAN.pth"
        if shutil.which("ffmpeg") is None:
            return "未找到 ffmpeg，可执行文件不在 PATH 中"
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
        model_path = resolve_existing_model_path()
        if model_path is None:
            raise RuntimeError("未找到 Wav2Lip 模型权重")
        self._validate_checkpoint(model_path)

        env = os.environ.copy()
        python_path_parts = [str(WAV2LIP_ROOT), str(PROJECT_ROOT)]
        if env.get("PYTHONPATH"):
            python_path_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(python_path_parts)

        wav2lip_batch_size = max(8, min(batch_size * 16, 128))
        face_det_batch_size = max(2, min(batch_size * 2, 16))
        # Resolve to absolute paths so cwd=WAV2LIP_ROOT does not redirect them
        avatar_abs = Path(avatar_path).resolve()
        audio_abs = Path(audio_path).resolve()
        output_abs = Path(output_path).resolve()
        cmd = [
            sys.executable,
            str(INFERENCE_SCRIPT),
            "--checkpoint_path",
            str(model_path),
            "--face",
            str(avatar_abs),
            "--audio",
            str(audio_abs),
            "--outfile",
            str(output_abs),
            "--pads",
            "0",
            "15",
            "0",
            "0",
            "--face_det_batch_size",
            str(face_det_batch_size),
            "--wav2lip_batch_size",
            str(wav2lip_batch_size),
        ]

        if use_super_resolution:
            logger.info("Wav2Lip 当前未启用额外超分，保留 use_super_resolution 标记")

        logger.info("启动 Wav2Lip 推理: {}", " ".join(cmd))
        task.update(progress=30, message="正在启动 AI 唇形同步引擎")
        with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", errors="ignore", delete=False, suffix=".log") as log_file:
            log_path = Path(log_file.name)
            proc = subprocess.Popen(
                cmd,
                cwd=str(WAV2LIP_ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )

        task.update(progress=68, message="AI 模型推理中")
        return_code = proc.wait()
        if return_code != 0:
            output_lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines() if log_path.exists() else []
            raise RuntimeError("Wav2Lip 推理失败: " + "\n".join(output_lines[-40:]))
        if not output_abs.is_file() or output_abs.stat().st_size == 0:
            raise RuntimeError("Wav2Lip 推理未生成输出文件")
        log_path.unlink(missing_ok=True)
        task.update(progress=90, message="正在整理 AI 唇形同步输出")