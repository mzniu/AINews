"""Shared LaMa inpainting for manual and automatic watermark removal."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger
from PIL import Image, ImageDraw


def _make_mock_lama():
    class MockLamaModel:
        def __call__(self, image, mask):
            return image.copy()

    return MockLamaModel()


def is_mock_lama(model: Any) -> bool:
    return type(model).__name__ == "MockLamaModel"


def get_lama_model():
    """获取LaMa去水印模型实例。先尝试 CUDA，失败则回退到 CPU。"""
    import os

    import torch

    try:
        from simple_lama_inpainting import SimpleLama
    except ImportError as e:
        logger.warning(f"LaMa模型未安装: {e}，使用模拟实现")
        return _make_mock_lama()

    if torch.cuda.is_available():
        try:
            model = SimpleLama(device="cuda")
            if hasattr(model, "to"):
                model = model.to("cuda")
            logger.info("LaMa模型加载成功 (GPU加速模式)")
            return model
        except Exception as cuda_err:
            logger.warning(f"CUDA 模式初始化失败，回退到 CPU: {cuda_err}")

    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    _orig_jit_load = torch.jit.load
    try:

        def _cpu_jit_load(f, *args, **kwargs):
            kwargs.setdefault("map_location", torch.device("cpu"))
            return _orig_jit_load(f, *args, **kwargs)

        torch.jit.load = _cpu_jit_load
        model = SimpleLama(device="cpu")
        if hasattr(model, "to"):
            model = model.to("cpu")
        logger.info("LaMa模型加载成功 (CPU模式)")
        return model
    except Exception as e:
        logger.error(f"LaMa模型加载失败: {e}")
        return _make_mock_lama()
    finally:
        torch.jit.load = _orig_jit_load


def _region_box(region: Any) -> tuple[int, int, int, int] | None:
    if hasattr(region, "x"):
        x = int(getattr(region, "x", 0))
        y = int(getattr(region, "y", 0))
        w = int(getattr(region, "width", 0))
        h = int(getattr(region, "height", 0))
    else:
        x = int(region.get("x", 0))
        y = int(region.get("y", 0))
        w = int(region.get("width", 0))
        h = int(region.get("height", 0))
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def inpaint_regions(
    image_path: Path | str,
    regions: Any,
    *,
    output_stem_suffix: str,
    expand_px: int = 5,
    allow_mock: bool = True,
) -> Path:
    src = Path(image_path)
    model = get_lama_model()
    if not allow_mock and is_mock_lama(model):
        raise RuntimeError("lama_unavailable")

    img = Image.open(src).convert("RGB")
    img_width, img_height = img.size
    mask = Image.new("L", (img_width, img_height), 0)
    mask_draw = ImageDraw.Draw(mask)
    for region in regions or ():
        box = _region_box(region)
        if box is None:
            continue
        x, y, w, h = box
        x1 = max(0, x - expand_px)
        y1 = max(0, y - expand_px)
        x2 = min(img_width, x + w + expand_px)
        y2 = min(img_height, y + h + expand_px)
        mask_draw.rectangle([(x1, y1), (x2, y2)], fill=255)

    result = model(img, mask)
    output_dir = src.parent / "watermark_removed"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{src.stem}{output_stem_suffix}{src.suffix}"
    result.save(output_path, quality=95)
    return output_path
