"""Detect watermark boxes and clean stills before video/cover render."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

PROMPT_VERSION = "wm_box_v1"
MAX_EDGE_PX = 1280
MAX_AREA_RATIO = 0.20
MIN_BOX_PX = 8
MASK_EXPAND_PX = 8
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int
    kind: str = "unknown"


def encoded_size(src_w: int, src_h: int, max_edge_px: int = MAX_EDGE_PX) -> tuple[int, int]:
    longest = max(src_w, src_h)
    if longest <= max_edge_px:
        return src_w, src_h
    scale = max_edge_px / longest
    return max(1, int(src_w * scale)), max(1, int(src_h * scale))


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _units_for(values: list[float]) -> str | None:
    has_fraction = any(0.0 < item <= 1.0 for item in values)
    has_pixel = any(item > 1.0 for item in values)
    if has_fraction and has_pixel:
        return None
    if not has_pixel:
        return "normalized"
    return "encoded_px"


def project_regions(payload: dict[str, Any], *, src_w: int, src_h: int) -> tuple[Region, ...]:
    if not payload.get("has_watermark", True):
        return ()
    raw_items = payload.get("regions") or []
    if not isinstance(raw_items, list):
        return ()
    enc_w, enc_h = encoded_size(src_w, src_h)
    out: list[Region] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        nums = [_as_float(item.get(key)) for key in ("x", "y", "width", "height")]
        if any(value is None for value in nums):
            continue
        x, y, w, h = (value for value in nums)
        units = _units_for([x, y, w, h])
        if units is None:
            continue
        if units == "normalized":
            x, y, w, h = x * enc_w, y * enc_h, w * enc_w, h * enc_h
        scale_x = src_w / enc_w
        scale_y = src_h / enc_h
        px = int(round(x * scale_x))
        py = int(round(y * scale_y))
        pw = int(round(w * scale_x))
        ph = int(round(h * scale_y))
        px = max(0, min(src_w - 1, px))
        py = max(0, min(src_h - 1, py))
        pw = max(0, min(src_w - px, pw))
        ph = max(0, min(src_h - py, ph))
        if pw < MIN_BOX_PX or ph < MIN_BOX_PX:
            continue
        if (pw * ph) > (src_w * src_h * MAX_AREA_RATIO):
            continue
        out.append(
            Region(
                x=px,
                y=py,
                width=pw,
                height=ph,
                kind=str(item.get("kind") or "unknown"),
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class WatermarkCleanResult:
    path: str
    status: Literal["cleaned", "skipped", "failed"]
    original_path: str
    cleaned_path: str | None
    regions: tuple[Region, ...]
    reason: str


class VisionBoxAdapter(Protocol):
    def detect(self, image_path: Path) -> dict[str, Any]: ...

    def model_id(self) -> str: ...


class InpaintAdapter(Protocol):
    def inpaint(self, image_path: Path, regions: tuple[Region, ...], output_path: Path) -> Path: ...

    def is_available(self) -> bool: ...


def _normalize_key(path: str | Path) -> str:
    from src.utils.paths import to_data_url_path

    return to_data_url_path(path)


def _open_path(raw: str) -> Path | None:
    from src.utils.paths import resolve_local_asset_path

    candidate = Path(str(raw))
    if candidate.is_file():
        return candidate
    return resolve_local_asset_path(raw)


def is_static_cleanable(path: Path) -> bool:
    from services.ingestion.image_scorer import is_animation_raster

    if path.suffix.lower() in VIDEO_SUFFIXES:
        return False
    return not is_animation_raster(path)


def _sidecar_paths(src: Path) -> tuple[Path, Path]:
    out_dir = src.parent / "watermark_removed"
    return (
        out_dir / f"{src.stem}_auto_clean{src.suffix}",
        out_dir / f"{src.stem}_auto_clean.json",
    )


def _fingerprint(regions: tuple[Region, ...], model_id: str) -> dict[str, Any]:
    return {
        "prompt_version": PROMPT_VERSION,
        "model_id": model_id,
        "regions": [asdict(region) for region in regions],
    }


def _fingerprint_matches(meta_path: Path, fingerprint: dict[str, Any]) -> bool:
    if not meta_path.is_file():
        return False
    try:
        stored = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return stored == fingerprint


def _write_fingerprint(meta_path: Path, fingerprint: dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(fingerprint, ensure_ascii=False, indent=2), encoding="utf-8")


def _result(
    *,
    original_path: str,
    status: Literal["cleaned", "skipped", "failed"],
    reason: str,
    cleaned_path: str | None = None,
    regions: tuple[Region, ...] = (),
) -> WatermarkCleanResult:
    path = cleaned_path if status == "cleaned" and cleaned_path else original_path
    return WatermarkCleanResult(
        path=path,
        status=status,
        original_path=original_path,
        cleaned_path=cleaned_path,
        regions=regions,
        reason=reason,
    )


class _DefaultInpaint:
    def is_available(self) -> bool:
        from services.watermark_inpaint import get_lama_model, is_mock_lama

        return not is_mock_lama(get_lama_model())

    def inpaint(self, image_path: Path, regions: tuple[Region, ...], output_path: Path) -> Path:
        from services.watermark_inpaint import inpaint_regions

        written = inpaint_regions(
            image_path,
            regions,
            output_stem_suffix="_auto_clean",
            expand_px=MASK_EXPAND_PX,
            allow_mock=False,
        )
        if written != output_path and written.is_file() and written != output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(written.read_bytes())
            return output_path
        return written


class _DefaultVision:
    def __init__(self, client: Any, profile: dict[str, Any]):
        self.client = client
        self.profile = profile

    def model_id(self) -> str:
        return str(self.profile.get("model") or "vision")

    def detect(self, image_path: Path) -> dict[str, Any]:
        from services.ingestion.image_score_vl import _encode_image_data_url, _load_json_payload
        from services.model_config.token_usage import complete_chat

        prompt = (
            "找出图中的台标、来源字、角标、半透明 logo、二维码。"
            "不要框正文、人脸或图表数字。"
            "只返回 JSON："
            '{"has_watermark": true, "regions": '
            '[{"x":0.0,"y":0.0,"width":0.1,"height":0.1,"kind":"logo"}]}。'
            "坐标相对你看到的图，优先用 0 到 1 的归一化框。"
        )
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": _encode_image_data_url(image_path, max_edge_px=MAX_EDGE_PX)},
            },
        ]
        request_kwargs: dict[str, Any] = {
            "model": self.profile["model"],
            "messages": [{"role": "user", "content": content}],
            "max_tokens": int(self.profile.get("max_tokens") or 1024),
            "temperature": float(
                self.profile.get("temperature") if self.profile.get("temperature") is not None else 0.1
            ),
            "timeout": int(self.profile.get("timeout") or 60),
        }
        if self.profile.get("json_mode", True):
            request_kwargs["response_format"] = {"type": "json_object"}
        try:
            response = complete_chat(
                self.client,
                kind="vision",
                profile=self.profile,
                task="watermark_box",
                **request_kwargs,
            )
        except Exception:
            request_kwargs.pop("response_format", None)
            response = complete_chat(
                self.client,
                kind="vision",
                profile=self.profile,
                task="watermark_box",
                **request_kwargs,
            )
        raw = response.choices[0].message.content or ""
        parsed = _load_json_payload(raw)
        return parsed if isinstance(parsed, dict) else {"has_watermark": False, "regions": []}


def _resolve_vision(vision: VisionBoxAdapter | None) -> VisionBoxAdapter | str:
    if vision is not None:
        return vision
    from services.model_config.registry import get_vision_client

    client, profile = get_vision_client()
    if client is None or not profile:
        return "vision_unavailable"
    return _DefaultVision(client, profile)


def clean_images_for_render(
    image_paths: list[str],
    *,
    enabled: bool = True,
    vision: VisionBoxAdapter | None = None,
    inpaint: InpaintAdapter | None = None,
) -> dict[str, WatermarkCleanResult]:
    results: dict[str, WatermarkCleanResult] = {}
    painter = inpaint or _DefaultInpaint()
    resolved_vision: VisionBoxAdapter | str | None = None

    for raw in image_paths:
        key = _normalize_key(raw)
        if not key or key in results:
            continue
        if not enabled:
            results[key] = _result(original_path=key, status="skipped", reason="disabled")
            continue
        src = _open_path(raw)
        if src is None:
            results[key] = _result(original_path=key, status="failed", reason="missing_file")
            continue
        if not is_static_cleanable(src):
            results[key] = _result(original_path=key, status="skipped", reason="not_static")
            continue
        if resolved_vision is None:
            resolved_vision = _resolve_vision(vision)
        if isinstance(resolved_vision, str):
            results[key] = _result(original_path=key, status="skipped", reason=resolved_vision)
            continue
        try:
            payload = resolved_vision.detect(src)
        except Exception:
            results[key] = _result(original_path=key, status="failed", reason="vl_error")
            continue
        from PIL import Image

        with Image.open(src) as img:
            src_w, src_h = img.size
        regions = project_regions(payload if isinstance(payload, dict) else {}, src_w=src_w, src_h=src_h)
        if not regions:
            results[key] = _result(original_path=key, status="skipped", reason="no_regions")
            continue
        cleaned_file, meta_file = _sidecar_paths(src)
        fingerprint = _fingerprint(regions, resolved_vision.model_id())
        if (
            cleaned_file.is_file()
            and cleaned_file.stat().st_mtime >= src.stat().st_mtime
            and _fingerprint_matches(meta_file, fingerprint)
        ):
            cleaned_key = _normalize_key(cleaned_file)
            results[key] = _result(
                original_path=key,
                status="cleaned",
                reason="reused",
                cleaned_path=cleaned_key,
                regions=regions,
            )
            continue
        if not painter.is_available():
            results[key] = _result(original_path=key, status="failed", reason="lama_unavailable")
            continue
        try:
            written = painter.inpaint(src, regions, cleaned_file)
        except RuntimeError as exc:
            reason = "lama_unavailable" if "lama_unavailable" in str(exc) else "inpaint_error"
            results[key] = _result(original_path=key, status="failed", reason=reason)
            continue
        except OSError:
            results[key] = _result(original_path=key, status="failed", reason="write_error")
            continue
        except Exception:
            results[key] = _result(original_path=key, status="failed", reason="inpaint_error")
            continue
        try:
            _write_fingerprint(meta_file, fingerprint)
        except OSError:
            results[key] = _result(original_path=key, status="failed", reason="write_error")
            continue
        results[key] = _result(
            original_path=key,
            status="cleaned",
            reason="ok",
            cleaned_path=_normalize_key(written),
            regions=regions,
        )
    return results
