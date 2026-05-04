from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AINews IndexTTS batch synthesis worker")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--segments-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prompt-audio", required=True)
    parser.add_argument("--device", default=None)
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--use-cuda-kernel", action="store_true")
    parser.add_argument("--fast", action="store_true")
    return parser.parse_args()


def _compatible_config_path(project_dir: Path, output_dir: Path) -> Path:
    """Write a config copy with GPT keys unsupported by this bundled code removed."""
    cfg_path = project_dir / "checkpoints" / "config.yaml"
    from omegaconf import OmegaConf
    from indextts.gpt.model import UnifiedVoice

    cfg = OmegaConf.load(cfg_path)
    accepted = set(inspect.signature(UnifiedVoice.__init__).parameters)
    accepted.discard("self")
    extra = [key for key in cfg.gpt.keys() if key not in accepted]
    if not extra:
        return cfg_path
    for key in extra:
        cfg.gpt.pop(key, None)
    sanitized = output_dir / "indextts_config_compat.yaml"
    OmegaConf.save(cfg, sanitized)
    print(f">> Removed unsupported GPT config keys for this IndexTTS build: {extra}")
    return sanitized


def _load_tts(project_dir: Path, output_dir: Path, args: argparse.Namespace):
    """Prefer the external app's compiled IndexTTS2 runtime; fall back to pure Python IndexTTS."""
    try:
        import kelong_tts2

        tts = getattr(kelong_tts2, "tts", None)
        if tts is not None:
            print(">> Using kelong_tts2 global IndexTTS2 runtime")
            return "v2", tts
        tts_cls = getattr(kelong_tts2, "IndexTTS2")
        print(">> Using kelong_tts2.IndexTTS2 runtime")
        return "v2", tts_cls(
            cfg_path="checkpoints/config.yaml",
            model_dir="checkpoints",
            is_fp16=bool(args.fp16),
            device=args.device,
            use_cuda_kernel=bool(args.use_cuda_kernel),
        )
    except Exception as exc:
        print(f">> kelong_tts2 unavailable, falling back to indextts.infer.IndexTTS: {exc}")

    from indextts.infer import IndexTTS

    cfg_path = _compatible_config_path(project_dir, output_dir)
    model_dir = project_dir / "checkpoints"
    return "v1", IndexTTS(
        cfg_path=str(cfg_path),
        model_dir=str(model_dir),
        is_fp16=bool(args.fp16),
        device=args.device,
        use_cuda_kernel=bool(args.use_cuda_kernel),
    )


def _resolve_worker_path(raw_path: str, *, launch_dir: Path, repo_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    launch_path = (launch_dir / path).resolve()
    if launch_path.exists():
        return launch_path
    repo_path = (repo_dir / path).resolve()
    if repo_path.exists() or repo_path.parent.exists():
        return repo_path
    return launch_path


def main() -> int:
    args = _parse_args()
    launch_dir = Path.cwd().resolve()
    repo_dir = Path(__file__).resolve().parents[1]
    project_dir = Path(args.project_dir).resolve()
    segments_json = _resolve_worker_path(args.segments_json, launch_dir=launch_dir, repo_dir=repo_dir)
    output_dir = _resolve_worker_path(args.output_dir, launch_dir=launch_dir, repo_dir=repo_dir)
    prompt_audio = _resolve_worker_path(args.prompt_audio, launch_dir=launch_dir, repo_dir=repo_dir)

    if not project_dir.is_dir():
        raise FileNotFoundError(f"IndexTTS project dir not found: {project_dir}")
    if not segments_json.is_file():
        raise FileNotFoundError(f"Segments json not found: {segments_json}")
    if not prompt_audio.is_file():
        raise FileNotFoundError(f"Prompt audio not found: {prompt_audio}")

    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))

    with segments_json.open("r", encoding="utf-8") as f:
        segments = json.load(f)
    if not isinstance(segments, list):
        raise ValueError("segments json must be a list")

    output_dir.mkdir(parents=True, exist_ok=True)

    tts_mode, tts = _load_tts(project_dir, output_dir, args)

    for index, text in enumerate(segments):
        output_path = output_dir / f"seg_{index:03d}.wav"
        text = str(text or "").strip()
        if not text:
            continue
        if tts_mode == "v2":
            tts.infer(
                spk_audio_prompt=str(prompt_audio),
                text=text,
                output_path=str(output_path),
                verbose=False,
                max_text_tokens_per_sentence=120,
            )
        elif args.fast:
            tts.infer_fast(
                audio_prompt=str(prompt_audio),
                text=text,
                output_path=str(output_path),
                verbose=False,
            )
        else:
            tts.infer(
                audio_prompt=str(prompt_audio),
                text=text,
                output_path=str(output_path),
                verbose=False,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())