# Auto Watermark Clean Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 成片前对入选静帧和封面源图自动去水印：视觉模型出框，LaMa 修到 sidecar，成片读清洗路径，失败不挡成片。

**Architecture:** `clean_images_for_render` 是唯一外部 seam。管线在选图之后、开画之前调用一次；封面 `pick_best_cover_image` 只挑一次并并进待洗集合。LaMa 抽到 `services/watermark_inpaint.py`，手动接口复用。

**Tech Stack:** pytest, Pillow, 现有 `get_vision_client` / `simple_lama_inpainting`, FastAPI。

**Spec:** `docs/superpowers/specs/2026-09-24-auto-watermark-clean-design.md`（已批准）

## Global Constraints

- 不覆盖原图；sidecar 在 `{parent}/watermark_removed/{stem}_auto_clean{suffix}`
- 路径键与 `result.path` 一律 `to_data_url_path`
- 框相对送模图（长边 1280），再映射回原图像素；优先 0–1 归一化
- 面积 > 原图 20% 的框丢弃；最小框 8×8；自动 mask 外扩 8px（手动接口仍 5px）
- GIF / 动画 WebP / 视频：`skipped: not_static`，仍可进成片
- 清洗失败不写入管线 `errors`
- 自动路径拒绝 LaMa mock；手动 `/api/remove-watermark` 仍可 mock
- sidecar 复用必须比对指纹（regions + 模型 id + `wm_box_v1`），不能只看 mtime
- 不把 `detect_watermark_regions` 接入自动清洗
- 不改 `cover_retry`、资讯库选图、查看器手动画框流程
- 用户未要求则不 git commit（仓库规则优先于本计划里的 commit 步；跳过所有 Commit step）

## File map

| 文件 | 职责 |
|------|------|
| `services/ingestion/watermark_clean.py` | 出框解析、回投影、清洗编排 |
| `services/watermark_inpaint.py` | LaMa 加载与写 sidecar |
| `services/ingestion/media_pipeline.py` | 插入 `clean_watermarks`，封面只 pick 一次 |
| `services/ingestion/media_pipeline_trigger.py` | `auto_remove_watermark` 默认与 override |
| `api/routes/watermark_routes.py` | 改调共享 inpaint |
| `config/article_scoring.yaml` | 默认打开 |
| `tests/test_watermark_clean.py` | 几何 + 编排 |
| `tests/test_watermark_inpaint.py` | mock 拒绝 / 写盘 |
| `tests/test_media_pipeline_trigger.py` | 配置默认 |
| `tests/test_media_pipeline.py` | 路径替换与封面只 pick 一次 |
| `tests/test_watermark_routes.py` | 手动接口冒烟 |

---

### Task 1: Pipeline config flag

**Files:**
- Modify: `services/ingestion/media_pipeline_trigger.py`
- Modify: `config/article_scoring.yaml`（`post_score_automation.media_pipeline` 下加一行）
- Test: `tests/test_media_pipeline_trigger.py`

**Interfaces:**
- Consumes: 现有 `load_media_pipeline_config`
- Produces: `cfg["auto_remove_watermark"]` 默认 `True`；传入顶层 override 时生效

- [ ] **Step 1: Write the failing test**

在 `tests/test_media_pipeline_trigger.py` 的 `test_load_media_pipeline_config_defaults` 增加：

```python
    assert cfg["auto_remove_watermark"] is True
```

再加：

```python
def test_auto_remove_watermark_override():
    cfg = load_media_pipeline_config({"auto_remove_watermark": False})
    assert cfg["auto_remove_watermark"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_media_pipeline_trigger.py::test_load_media_pipeline_config_defaults tests/test_media_pipeline_trigger.py::test_auto_remove_watermark_override -q`

Expected: FAIL，`auto_remove_watermark` KeyError 或 override 无效。

- [ ] **Step 3: Minimal implementation**

`_FLAT_OVERRIDE_KEYS` 追加 `"auto_remove_watermark"`。

`load_media_pipeline_config` 的 `defaults` 增加：

```python
        "auto_remove_watermark": bool(pipeline.get("auto_remove_watermark", True)),
```

`config/article_scoring.yaml` 的 `media_pipeline` 增加：

```yaml
    auto_remove_watermark: true
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_media_pipeline_trigger.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

跳过（全局约束）。

---

### Task 2: Box parse and scale-back

**Files:**
- Create: `services/ingestion/watermark_clean.py`（先只放几何与类型）
- Test: `tests/test_watermark_clean.py`

**Interfaces:**
- Consumes: 无
- Produces:

```python
PROMPT_VERSION = "wm_box_v1"
MAX_EDGE_PX = 1280
MAX_AREA_RATIO = 0.20
MIN_BOX_PX = 8

@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int
    kind: str = "unknown"

def encoded_size(src_w: int, src_h: int, max_edge_px: int = MAX_EDGE_PX) -> tuple[int, int]: ...
def project_regions(
    payload: dict,
    *,
    src_w: int,
    src_h: int,
) -> tuple[Region, ...]: ...
```

- [ ] **Step 1: Write the failing tests**

创建 `tests/test_watermark_clean.py`：

```python
from services.ingestion.watermark_clean import encoded_size, project_regions


def test_encoded_size_shrinks_long_edge():
    assert encoded_size(2560, 1440) == (1280, 720)


def test_normalized_box_maps_to_source_pixels():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [
                {"x": 0.75, "y": 0.90, "width": 0.20, "height": 0.08, "kind": "logo"}
            ],
        },
        src_w=2560,
        src_h=1440,
    )
    assert len(regions) == 1
    box = regions[0]
    assert box.kind == "logo"
    assert 1900 <= box.x <= 1950
    assert 1280 <= box.y <= 1320
    assert 480 <= box.width <= 540
    assert 100 <= box.height <= 130


def test_encoded_pixel_box_maps_back_on_large_source():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [{"x": 960, "y": 648, "width": 256, "height": 58, "kind": "logo"}],
        },
        src_w=2560,
        src_h=1440,
    )
    assert len(regions) == 1
    box = regions[0]
    assert box.x == 1920
    assert box.y == 1296
    assert box.width == 512
    assert box.height == 116


def test_oversized_box_is_dropped():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [{"x": 0.0, "y": 0.0, "width": 0.9, "height": 0.9}],
        },
        src_w=800,
        src_h=600,
    )
    assert regions == ()


def test_mixed_units_are_dropped():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [{"x": 10, "y": 0.1, "width": 0.2, "height": 40}],
        },
        src_w=800,
        src_h=600,
    )
    assert regions == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_watermark_clean.py -q`

Expected: FAIL，模块不存在。

- [ ] **Step 3: Minimal implementation**

创建 `services/ingestion/watermark_clean.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    if all(0.0 <= item <= 1.0 for item in values):
        return "normalized"
    if all(item > 1.0 or item == 0.0 for item in values) or any(item > 1.0 for item in values):
        if all(item > 1.0 or item == 0.0 for item in values):
            return "encoded_px"
        if any(0.0 < item <= 1.0 for item in values) and any(item > 1.0 for item in values):
            return None
        return "encoded_px"
    return "normalized"


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
        x, y, w, h = nums
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
```

`_units_for` 必须把「有的 ≤1、有的 >1」判为混用并返回 `None`。`0` 允许出现在像素框里（贴边）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_watermark_clean.py -q`

Expected: PASS。若 `test_normalized_box_maps_to_source_pixels` 因四舍五入越界，按公式收紧断言而不是放宽门禁。

- [ ] **Step 5: Commit**

跳过。

---

### Task 3: Shared LaMa inpaint

**Files:**
- Create: `services/watermark_inpaint.py`
- Modify: `api/routes/watermark_routes.py`（`get_lama_model` 改为 re-export；`remove_watermark` 调 `inpaint_regions`）
- Create: `tests/test_watermark_inpaint.py`
- Create: `tests/test_watermark_routes.py`

**Interfaces:**
- Consumes: 现有 `watermark_routes.get_lama_model` 实现（原样搬家）
- Produces:

```python
def is_mock_lama(model: Any) -> bool: ...
def get_lama_model() -> Any: ...
def inpaint_regions(
    image_path: Path,
    regions: list[dict[str, int]] | tuple[Region, ...],
    *,
    output_stem_suffix: str,
    expand_px: int = 5,
    allow_mock: bool = True,
) -> Path: ...
```

自动清洗稍后以 `allow_mock=False`、`expand_px=8`、`output_stem_suffix="_auto_clean"` 调用。

- [ ] **Step 1: Write the failing tests**

`tests/test_watermark_inpaint.py`：

```python
from pathlib import Path

from PIL import Image

from services.watermark_inpaint import inpaint_regions, is_mock_lama


class _FakeLama:
    def __call__(self, image, mask):
        return image.copy()


def test_inpaint_writes_sidecar(tmp_path, monkeypatch):
    src = tmp_path / "shot.jpg"
    Image.new("RGB", (80, 80), (10, 20, 30)).save(src)
    monkeypatch.setattr("services.watermark_inpaint.get_lama_model", lambda: _FakeLama())
    out = inpaint_regions(
        src,
        [{"x": 4, "y": 4, "width": 10, "height": 10}],
        output_stem_suffix="_auto_clean",
        expand_px=8,
        allow_mock=False,
    )
    assert out.name == "shot_auto_clean.jpg"
    assert out.parent.name == "watermark_removed"
    assert src.read_bytes() != b""  # original still there
    assert out.is_file()


def test_auto_path_rejects_mock(tmp_path, monkeypatch):
    src = tmp_path / "shot.jpg"
    Image.new("RGB", (40, 40), (1, 2, 3)).save(src)

    class MockLama:
        def __call__(self, image, mask):
            return image

    model = MockLama()
    monkeypatch.setattr("services.watermark_inpaint.get_lama_model", lambda: model)
    monkeypatch.setattr("services.watermark_inpaint.is_mock_lama", lambda _model: True)
    try:
        inpaint_regions(
            src,
            [{"x": 1, "y": 1, "width": 8, "height": 8}],
            output_stem_suffix="_auto_clean",
            allow_mock=False,
        )
    except RuntimeError as exc:
        assert "lama_unavailable" in str(exc)
    else:
        raise AssertionError("expected lama_unavailable")
    assert not (src.parent / "watermark_removed" / "shot_auto_clean.jpg").exists()
```

`tests/test_watermark_routes.py`：

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from api.routes.watermark_routes import router


def test_manual_remove_watermark_smoke(tmp_path, monkeypatch):
    src = tmp_path / "manual.jpg"
    Image.new("RGB", (40, 40), (9, 9, 9)).save(src)

    class MockLama:
        def __call__(self, image, mask):
            return image.copy()

    monkeypatch.setattr("services.watermark_inpaint.get_lama_model", lambda: MockLama())
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post(
        "/api/remove-watermark",
        json={
            "image_path": str(src).replace("\\", "/"),
            "regions": [{"x": 2, "y": 2, "width": 8, "height": 8}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["regions_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_watermark_inpaint.py tests/test_watermark_routes.py -q`

Expected: FAIL，模块不存在或路由仍是旧实现。

- [ ] **Step 3: Minimal implementation**

把 `api/routes/watermark_routes.py` 里的 `_make_mock_lama` / `get_lama_model` 原样搬到 `services/watermark_inpaint.py`。增加：

```python
def is_mock_lama(model: Any) -> bool:
    return type(model).__name__ == "MockLamaModel"


def inpaint_regions(image_path, regions, *, output_stem_suffix, expand_px=5, allow_mock=True) -> Path:
    model = get_lama_model()
    if not allow_mock and is_mock_lama(model):
        raise RuntimeError("lama_unavailable")
    # 打开 RGB，画 mask，每边 expand_px，model(img, mask)
    # 写到 image_path.parent / "watermark_removed" / f"{stem}{suffix}{ext}"
    # regions 既接受 dict 也接受带 x/y/width/height 的对象
```

路由改为：

```python
from services.watermark_inpaint import get_lama_model, inpaint_regions

@router.post("/remove-watermark")
async def remove_watermark(request: RemoveWatermarkRequest):
    ...
    output_path = inpaint_regions(
        image_path,
        request.regions,
        output_stem_suffix=f"_clean_{timestamp}",
        expand_px=5,
        allow_mock=True,
    )
    # 保持现有 JSON 字段：cleaned_path / regions_count / original_path
```

`remove_watermark` 不要再自己画 mask。`get_lama_model` 从本模块 re-export，避免其它 import 漂移。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_watermark_inpaint.py tests/test_watermark_routes.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

跳过。

---

### Task 4: `clean_images_for_render`

**Files:**
- Modify: `services/ingestion/watermark_clean.py`
- Test: `tests/test_watermark_clean.py`

**Interfaces:**
- Consumes: Task 2 的 `project_regions` / `Region`；Task 3 的 `inpaint_regions`
- Produces:

```python
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

def clean_images_for_render(
    image_paths: list[str],
    *,
    enabled: bool = True,
    vision: VisionBoxAdapter | None = None,
    inpaint: InpaintAdapter | None = None,
) -> dict[str, WatermarkCleanResult]:
```

生产：`vision is None` 时 `get_vision_client`，没有 client 则全部 `vision_unavailable`。`inpaint is None` 时调 `inpaint_regions(..., allow_mock=False, expand_px=8, output_stem_suffix="_auto_clean")`。

- [ ] **Step 1: Write the failing tests**

追加到 `tests/test_watermark_clean.py`：

```python
from pathlib import Path

from PIL import Image

from services.ingestion.watermark_clean import clean_images_for_render
from src.utils.paths import to_data_url_path


class _Vision:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def model_id(self):
        return "vision-test"

    def detect(self, image_path: Path):
        self.calls += 1
        return self.payload


class _Inpaint:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def inpaint(self, image_path, regions, output_path):
        self.calls += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.open(image_path).save(output_path)
        return output_path


def _jpg(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 200), (80, 80, 80)).save(path)
    return path


def test_disabled_skips_without_io(tmp_path):
    src = _jpg(tmp_path / "a.jpg")
    vision = _Vision({"has_watermark": True, "regions": []})
    result = clean_images_for_render([str(src)], enabled=False, vision=vision)
    key = to_data_url_path(src)
    assert result[key].status == "skipped"
    assert result[key].reason == "disabled"
    assert vision.calls == 0


def test_gif_is_not_static(tmp_path):
    gif = tmp_path / "a.gif"
    Image.new("RGB", (40, 40), (1, 2, 3)).save(gif)
    result = clean_images_for_render(
        [str(gif)],
        vision=_Vision({"has_watermark": True, "regions": [{"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}]}),
        inpaint=_Inpaint(),
    )
    key = to_data_url_path(gif)
    assert result[key].status == "skipped"
    assert result[key].reason == "not_static"


def test_cleans_and_keeps_original(tmp_path):
    src = _jpg(tmp_path / "shot.jpg")
    before = src.read_bytes()
    inpaint = _Inpaint()
    result = clean_images_for_render(
        [str(src), str(src).replace("\\", "/")],
        vision=_Vision(
            {
                "has_watermark": True,
                "regions": [{"x": 0.7, "y": 0.8, "width": 0.2, "height": 0.1, "kind": "logo"}],
            }
        ),
        inpaint=inpaint,
    )
    key = to_data_url_path(src)
    assert len(result) == 1
    assert result[key].status == "cleaned"
    assert result[key].cleaned_path
    assert src.read_bytes() == before
    assert inpaint.calls == 1


def test_fingerprint_reuse_then_refresh(tmp_path):
    src = _jpg(tmp_path / "shot.jpg")
    vision = _Vision(
        {
            "has_watermark": True,
            "regions": [{"x": 0.7, "y": 0.8, "width": 0.2, "height": 0.1}],
        }
    )
    inpaint = _Inpaint()
    first = clean_images_for_render([str(src)], vision=vision, inpaint=inpaint)
    assert inpaint.calls == 1
    second = clean_images_for_render([str(src)], vision=vision, inpaint=inpaint)
    assert inpaint.calls == 1
    assert first[to_data_url_path(src)].path == second[to_data_url_path(src)].path
    vision.payload = {
        "has_watermark": True,
        "regions": [{"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}],
    }
    clean_images_for_render([str(src)], vision=vision, inpaint=inpaint)
    assert inpaint.calls == 2
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `python -m pytest tests/test_watermark_clean.py -q`

Expected: FAIL，`clean_images_for_render` 未定义。Task 2 的几何测试必须仍绿。

- [ ] **Step 3: Minimal implementation**

在 `watermark_clean.py` 追加编排：

1. `to_data_url_path` 去重。
2. `enabled=False` → `skipped: disabled`。
3. `is_static_cleanable`：视频后缀或 `is_animation_raster` → `not_static`。
4. `vision.detect` 得到 payload，用 Pillow 读 `src_w/src_h`，`project_regions`。
5. 无框 → `skipped: no_regions`。
6. sidecar + `{stem}_auto_clean.json` 指纹（`regions` 的 `asdict`、`model_id`、`PROMPT_VERSION`）一致且 sidecar mtime ≥ 原图 → 复用。
7. 否则 `inpaint.inpaint(...)`；生产默认 adapter 调 `inpaint_regions(..., allow_mock=False, expand_px=MASK_EXPAND_PX)`。
8. VL 异常 → `failed: vl_error`；inpaint `RuntimeError("lama_unavailable")` → `failed: lama_unavailable`；其它写盘/推理 → `failed: inpaint_error` 或 `write_error`。
9. `result.path`：cleaned 用清洗路径的 `to_data_url_path`，否则用原 normalize 路径。

生产 `vision is None`：`client, profile = get_vision_client()`；都缺则每张 `vision_unavailable`。真 VL 调用单张图，JSON 用 `_load_json_payload`，送模用 `_encode_image_data_url(..., max_edge_px=MAX_EDGE_PX)`。本任务测试全部走注入 adapter，可以先不做真 VL 网络调用，但默认分支必须写完。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_watermark_clean.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

跳过。

---

### Task 5: Hook media pipeline

**Files:**
- Modify: `services/ingestion/media_pipeline.py`
- Test: `tests/test_media_pipeline.py`

**Interfaces:**
- Consumes: `clean_images_for_render`、`cfg["auto_remove_watermark"]`、`to_data_url_path`
- Produces: `steps["clean_watermarks"]`；`render_ingested_video` / `render_article_cover` 收到 mapping 后的 path；`pick_best_cover_image` 每篇一次

- [ ] **Step 1: Write the failing test**

在 `tests/test_media_pipeline.py` 追加（沿用文件里已有 fixture / `_pipeline_test_image`）：

```python
@patch("services.ingestion.media_pipeline.clean_images_for_render")
@patch("services.ingestion.media_pipeline.prepend_cover_intro_to_video")
@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.pick_best_cover_image")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_uses_cleaned_paths_and_picks_cover_once(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_pick_cover,
    mock_cover,
    mock_intro,
    mock_clean,
    db_session,
):
    from services.ingestion.watermark_clean import WatermarkCleanResult

    hero = _pipeline_test_image("hero.jpg")
    cover = _pipeline_test_image("cover.jpg")
    mock_score.return_value = {"scored_count": 1, "from_cache": True}
    mock_content.return_value = {
        "success": True,
        "main_line1": "突发！",
        "summary": "小牛说：x",
        "tags": "#AI",
        "model": "m",
    }
    mock_prepare.return_value = {
        "auto_selected_images": [hero],
        "images": [hero],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/out.mp4"}
    mock_pick_cover.return_value = cover
    mock_cover.return_value = {"success": True, "cover_path": "data/publish/covers/out.jpg"}
    mock_intro.return_value = {"success": True, "video_path": "/data/videos/out.mp4"}

    cleaned_hero = "/data/hero_auto_clean.jpg"
    cleaned_cover = "/data/cover_auto_clean.jpg"

    def _clean(paths, *, enabled=True, **kwargs):
        assert enabled is True
        return {
            path: WatermarkCleanResult(
                path=cleaned_hero if "hero" in path else cleaned_cover,
                status="cleaned",
                original_path=path,
                cleaned_path=cleaned_hero if "hero" in path else cleaned_cover,
                regions=(),
                reason="ok",
            )
            for path in paths
        }

    mock_clean.side_effect = _clean

    result = run_media_pipeline(db_session, "art_pipe")
    assert result["success"] is True
    assert mock_pick_cover.call_count == 1
    sent_images = mock_render.call_args.kwargs.get("image_paths") or mock_render.call_args[1].get("image_paths")
    if sent_images is None:
        sent_images = mock_render.call_args[0][2] if len(mock_render.call_args[0]) > 2 else mock_render.call_args.kwargs["image_paths"]
    assert cleaned_hero in sent_images
    cover_path = mock_cover.call_args.kwargs.get("image_path")
    if cover_path is None:
        cover_path = mock_cover.call_args[1]["image_path"]
    assert cover_path == cleaned_cover
    assert "clean_watermarks" in result["steps"]
    assert "clean_watermarks:" not in " ".join(result.get("errors") or [])
```

若 `run_media_pipeline` 返回结构没有 `steps`，改断言 `result` 里已有的 steps 字段（先读 `run_media_pipeline` 的 return）。现实现 return 含 `steps`。

- [ ] **Step 2: Run the new test to verify it fails**

Run: `python -m pytest tests/test_media_pipeline.py::test_pipeline_uses_cleaned_paths_and_picks_cover_once -q`

Expected: FAIL，`clean_images_for_render` 未被调用或封面 pick 两次。

- [ ] **Step 3: Minimal pipeline hook**

在 `media_pipeline.py`：

1. `from services.ingestion.watermark_clean import clean_images_for_render`
2. 选图写完 `selected_images_json` 之后：`cover_source = pick_best_cover_image(...)`（后面 `render_cover` 复用这个变量，删掉第二次调用）。
3. 收集 normalize 后的 selected + cover 路径，调用 `clean_images_for_render(..., enabled=bool(cfg.get("auto_remove_watermark", True)))`。
4. 回写 `cleaned_path` / `watermark_clean`；`image_paths` 用 `result.path`。
5. `render_cover` 的 `image_path` 用 mapping；缺则原 normalize 路径。
6. `steps["clean_watermarks"] = {path: {"status", "reason"} for ...}`，失败不 `errors.append`。
7. 本步异常只 warning，全部回退原路径，不挡成片。

现有 `@patch(...pick_best_cover_image)` 的测试应仍通过（调用次数从可能的 1 变为必须 1）。没有 patch pick 的测试会走真 pick，行为不变。

- [ ] **Step 4: Run pipeline tests**

Run: `python -m pytest tests/test_media_pipeline.py tests/test_watermark_clean.py tests/test_media_pipeline_trigger.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

跳过。

---

### Task 6: Spec coverage sweep

**Files:**
- 不新增功能。只补缺测并跑全相关套件。

**Interfaces:**
- Consumes: 上面全部
- Produces: 规格验收项都有测试指向

- [ ] **Step 1: Add missing tests if any gap remains**

确认已覆盖：

- 原图 >1280 的像素框回投影（Task 2）
- 路径去重（Task 4 `str(src)` 两次）
- GIF `not_static`（Task 4）
- 指纹变化重洗（Task 4）
- 自动 mock 拒绝（Task 3）
- 手动路由冒烟（Task 3）
- 管线路径替换 + 封面只 pick 一次（Task 5）
- 配置默认 / override（Task 1）

若 `clean_images_for_render` 在 `vision is None` 且 client 为 None 时未测，补：

```python
def test_missing_vision_skips(tmp_path, monkeypatch):
    src = _jpg(tmp_path / "a.jpg")
    monkeypatch.setattr(
        "services.ingestion.watermark_clean.get_vision_client",
        lambda: (None, None),
    )
    result = clean_images_for_render([str(src)])
    assert result[to_data_url_path(src)].reason == "vision_unavailable"
```

- [ ] **Step 2: Run the full related suite**

Run: `python -m pytest tests/test_watermark_clean.py tests/test_watermark_inpaint.py tests/test_watermark_routes.py tests/test_media_pipeline.py tests/test_media_pipeline_trigger.py -q`

Expected: PASS

- [ ] **Step 3: Commit**

跳过。

---

## Self-review

1. **Spec coverage:** 送模回投影、路径归一化、GIF 策略、指纹复用、可注入 seam、封面只 pick 一次、fail-open、LaMa 抽取、配置开关均有对应任务。`cover_retry` 明确不改。
2. **Placeholders:** 无 TBD。Commit 步按仓库规则跳过。
3. **Types:** `Region` / `WatermarkCleanResult` / `clean_images_for_render` 在 Task 2–5 名称一致。
