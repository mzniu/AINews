"""Select and invoke the best available lip-sync engine.

Priority: EchoMimic V2 > MuseTalk 1.5 > Wav2Lip (fallback)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from loguru import logger
from services.lip_sync.echomimic_engine import EchoMimicV2Engine
from services.lip_sync.musetalk_engine import MuseTalkEngine
from services.lip_sync.wav2lip_engine import Wav2LipEngine

AnyEngine = Union[EchoMimicV2Engine, MuseTalkEngine, Wav2LipEngine]


class LipSyncEngineManager:
    def __init__(self) -> None:
        self._echomimic = EchoMimicV2Engine()
        self._musetalk = MuseTalkEngine()
        self._wav2lip = Wav2LipEngine()

    def _best_engine(self) -> AnyEngine:
        """Return best available engine: EchoMimic > MuseTalk > Wav2Lip."""
        if self._echomimic.is_available():
            logger.info("使用 EchoMimic V2 引擎")
            return self._echomimic
        em_reason = self._echomimic.availability_reason()
        logger.info("EchoMimic V2 不可用 ({}), 尝试 MuseTalk", em_reason)
        if self._musetalk.is_available():
            logger.info("使用 MuseTalk 1.5 引擎")
            return self._musetalk
        mt_reason = self._musetalk.availability_reason()
        logger.info("MuseTalk 不可用 ({}), 尝试 Wav2Lip 作为后备", mt_reason)
        return self._wav2lip

    def _requested_engine(self, engine_preference: str) -> AnyEngine:
        preference = (engine_preference or "auto").strip().lower()
        if preference == "auto":
            return self._best_engine()
        if preference == "echomimic":
            logger.info("按用户选择使用 EchoMimic V2 引擎")
            return self._echomimic
        if preference == "musetalk":
            logger.info("按用户选择使用 MuseTalk 1.5 引擎")
            return self._musetalk
        if preference == "wav2lip":
            logger.info("按用户选择使用 Wav2Lip 引擎")
            return self._wav2lip
        raise RuntimeError(f"未知 AI 唇形同步引擎: {engine_preference}")

    def ensure_ai_available(self, engine_preference: str = "auto") -> AnyEngine:
        engine = self._requested_engine(engine_preference)
        reason = engine.availability_reason()
        if reason is not None:
            raise RuntimeError(f"AI 唇形同步当前不可用: {reason}")
        return engine

    def run_ai(
        self,
        avatar_path: Path,
        audio_path: Path,
        output_path: Path,
        task: Any,
        batch_size: int,
        use_super_resolution: bool,
        engine_preference: str = "auto",
    ) -> str:
        engine = self.ensure_ai_available(engine_preference)
        engine.run(
            avatar_path=avatar_path,
            audio_path=audio_path,
            output_path=output_path,
            task=task,
            batch_size=batch_size,
            use_super_resolution=use_super_resolution,
        )
        return engine.name


lip_sync_engine_manager = LipSyncEngineManager()