# 成片前自动去水印

## 目标

成片前自动清掉入选配图上的台标、来源字、角标水印。原图保留，成片和封面用清洗图。失败不挡成片。

不改资讯库选图，不改查看器手动画框去水印。`cover_retry` 等绕过媒体管线的入口也不洗。

## 核心决策

- 时机：媒体管线里选图完成之后、封面和视频开画之前。
- 范围：本篇最终入选配图，外加封面源图（封面经常不是同一张）。`pick_best_cover_image` 只调用一次，清洗和渲封面共用结果。
- 检测：设置里的视觉模型直接框出水印，不用现有角标 CV 当主检测。
- 修复：复用现有 LaMa。
- 落盘：sidecar，不覆盖原文件。成片读清洗路径，没有或失败回退原路径。
- 路径契约：入参、mapping 键、`result.path` 一律 `to_data_url_path`，与 `_normalize_local_path` 同形。
- 开关：`media_pipeline.auto_remove_watermark`，默认 `true`。`load_media_pipeline_config` 的 defaults 与 `_FLAT_OVERRIDE_KEYS` 都要加。视觉模型没配好则整步跳过。

## 架构

一个深模块扛全部清洗逻辑，管线只传路径、收回映射。

```
prepare_video（选出 selected_images）
        │
        ▼
pick_best_cover_image     ← 提前一次，清洗与封面共用
        │
        ▼
clean_watermarks
        │  unique(selected + cover)，键已 normalize
        │  VL 出框 → 映射回原图像素 → 校验 → LaMa → sidecar
        ▼
render_video / render_cover   只用 result.path
```

### 模块与接口

`services/ingestion/watermark_clean.py` 是唯一外部 seam。可选 adapter 只为测试注入，生产不传：

```python
@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int
    kind: str = "unknown"


@dataclass(frozen=True)
class WatermarkCleanResult:
    path: str                 # 成片应使用的路径（已 normalize）
    status: Literal["cleaned", "skipped", "failed"]
    original_path: str
    cleaned_path: str | None
    regions: tuple[Region, ...]
    reason: str


def clean_images_for_render(
    image_paths: list[str],
    *,
    enabled: bool = True,
    vision: VisionBoxAdapter | None = None,
    inpaint: InpaintAdapter | None = None,
) -> dict[str, WatermarkCleanResult]:
    """键与 result.path 均为 to_data_url_path。失败时 path == 原路径。"""
```

调用方只依赖 `result.path` 和 `result.status`。框选解析、送模缩放回投影、面积门禁、sidecar 指纹复用、LaMa 加载都藏在模块里。

LaMa 从 `api/routes/watermark_routes.py` 抽到 `services/watermark_inpaint.py`：

- `get_lama_model()` — 现有 CUDA / CPU / mock 逻辑原样搬家
- `inpaint_regions(image_path, regions, *, output_stem_suffix: str) -> Path` — 自动用 `_auto_clean`，手动用 `_clean_{timestamp}`
- 路由保留 `get_lama_model = watermark_inpaint.get_lama_model` 薄 re-export
- 自动路径拒绝 mock（视为 `lama_unavailable`）；手动 `/api/remove-watermark` 仍可 mock

视觉出框留在清洗模块内，复用 `get_vision_client`、`_encode_image_data_url`、`_load_json_payload`。不复用配图评分的 prompt。

现有 `detect_watermark_regions`（角标 CV）仍只给配图评分扣分和查看器「检测」按钮用，不接入自动清洗。

### 管线接入

`services/ingestion/media_pipeline.py` 在写完 `selected_images_json` 之后、渲视频 / 封面之前：

1. `cover_source = pick_best_cover_image(...)`，后面 `render_cover` 复用，不再挑第二次。
2. 待洗路径 = 入选图 `local_path` ∪ 封面 `local_path`，全部 `to_data_url_path` 后去重。
3. 静帧判定用后缀 + `is_animated`（可复用 `image_scorer` 的动画判定）。**不**跟 `filter_renderable_image_dicts` 绑：后者不过滤 GIF，成片仍可吃动图，但自动清洗对 GIF / 视频 / 动画 WebP 记 `skipped: not_static`。
4. `results = clean_images_for_render(paths, enabled=cfg["auto_remove_watermark"])`。
5. 回写每条入选图：`cleaned_path`、`watermark_clean={status, reason, regions}`。
6. 成片 `image_paths` 与封面 `image_path` 都用 `results[normalized].path`；缺键则回退 normalize 后的原路径。
7. `steps["clean_watermarks"]` 记每张图的 status，不把失败推进 `errors`。

手动「重新出片」沿用默认开关，不必另开 UI。

## 数据流

### 视觉模型出框

单张图一次调用。Prompt 要求只标台标、来源字、角标、半透明 logo、二维码；不标正文、人脸、图表数字。

送模图是 `_encode_image_data_url(..., max_edge_px=1280)` 压过长边的图。模型看见的尺寸可能小于原图。

约定 JSON：框相对**送模图**，左上原点。优先归一化 0–1（`x,y,width,height` 均在 `[0, 1]`）。也接受送模图像素。

```json
{
  "has_watermark": true,
  "regions": [
    {"x": 0.76, "y": 0.91, "width": 0.20, "height": 0.06, "kind": "logo"}
  ]
}
```

回投影到原图：

1. 记录原图 `(src_w, src_h)` 与送模图 `(enc_w, enc_h)`。
2. 若四值都 ≤ 1：视为归一化，先乘 `enc_*` 再按 `src/enc` 放大。
3. 否则视为送模图像素，乘 `src_w/enc_w`、`src_h/enc_h`。
4. 四舍五入成整数后 clamp 到原图。
5. `x/y` 与 `width/height` 不得混用两套单位；混用或无法判定则丢弃该框。

门禁（相对**原图**，任一不满足则丢弃该框）：

- `width >= 8` 且 `height >= 8`
- 面积 ≤ 原图面积的 20%
- 坐标在图内

修复前每边外扩 **8px**（手动接口仍是 5px，只是同量级，不要求数值一致）。

全部框被丢弃或 `has_watermark=false`：`skipped`，用原图。

每篇约 3–5 次 VL。超时沿用视觉 profile；单张失败不影响其余图。

### Sidecar

路径：`{original.parent}/watermark_removed/{stem}_auto_clean{suffix}`。  
指纹：同目录 `{stem}_auto_clean.json`，写入 `regions`、模型 id、prompt 版本。

复用条件（同时满足才跳过 LaMa）：

- sidecar 存在且 mtime ≥ 原图 mtime
- 指纹文件存在且 `regions` + 模型 id + prompt 版本与本次一致

区域或模型变了必须重洗。要强制重洗：删 sidecar 与指纹，或换原图。

原图、资讯库 `ArticleImage.local_path`、查看器缩略图都不改。

### 封面

封面源经常不在入选 3–4 张里。同一步并进待洗集合。封面成片（合成画面）不再洗。仅自动 `run_media_pipeline` 走这一步；`cover_retry` 不洗。

## 错误处理

| 情况 | 行为 |
|---|---|
| 开关关闭 | 全部 `skipped: disabled`，path=原图 |
| 视觉模型未配置 / client 为 None | 全部 `skipped: vision_unavailable`，不调用 LaMa |
| 单张 VL 超时或非 JSON | 该张 `failed: vl_error`，其余继续 |
| 无有效框 | `skipped: no_regions` |
| GIF / 动画 WebP / 视频 | `skipped: not_static`（仍可进成片） |
| 自动路径 LaMa 为 mock | `failed: lama_unavailable`，不写 sidecar |
| LaMa 推理失败 | `failed: inpaint_error` |
| sidecar 写盘失败 | `failed: write_error` |

原则：清洗失败 ≠ 成片失败。管线继续，日志 warning。

## 配置

`config/article_scoring.yaml` 的 `post_score_automation.media_pipeline`：

```yaml
auto_remove_watermark: true
```

模块内常量（暂不做成可配）：

- 送模长边：1280（与 `_encode_image_data_url` 默认一致）
- 最大框面积比：0.20（相对原图）
- 最小框：8×8
- mask 外扩：8px
- prompt 版本：`wm_box_v1`（写入指纹）

## 测试

通过 `vision` / `inpaint` adapter 注入，不打真实模型。

- 原图长边 >1280 时，送模图像素框回投影后 mask 对准原图角标。
- 归一化 0–1 框换算正确。
- 超大框（>20% 原图）被丢弃。
- 混用归一化与像素的框被丢弃。
- `enabled=false` 或 vision 为 None：不读图、不写 sidecar。
- 路径键：`data/...`、`/data/...`、相对路径归一化后能命中同一条 result。
- GIF / 动画 WebP → `not_static`，且管线仍可把它送去成片。
- sidecar+指纹一致：不二次 inpaint；区域或模型变了：必须重洗。
- 自动路径 mock inpaint → `lama_unavailable`，path 仍是原图。
- 管线：提前 pick 一次封面；`render_ingested_video` / `render_article_cover` 收到 mapping 里的 path。
- `load_media_pipeline_config` 默认带上 `auto_remove_watermark=true`。
- 抽出 LaMa 后补一条手动 `/api/remove-watermark` 冒烟（仍可 mock）。

## 非目标

- 资讯库批量清洗、查看器「一键检测并去除」
- 用 CV 角标检测给自动清洗出框
- 成片后再去水印、或去视频帧水印
- 覆盖原图
- 清洗失败阻断成片
- 改配图评分的 watermark 预过滤
- `cover_retry` 及其它绕过 `run_media_pipeline` 的入口

## 文件变更

- `services/ingestion/watermark_clean.py` — 新模块
- `services/watermark_inpaint.py` — LaMa 共享
- `services/ingestion/media_pipeline.py` — 插入步骤，封面只 pick 一次
- `services/ingestion/media_pipeline_trigger.py` — defaults + override key
- `api/routes/watermark_routes.py` — 改为调用共享 inpaint
- `config/article_scoring.yaml` — 默认打开
- `tests/test_watermark_clean.py` — 新测试
- `tests/test_media_pipeline.py` — 断言路径替换与封面只 pick 一次

## 验收

1. 配好视觉模型后走自动媒体管线成片，入选静帧若有角标，成片里应消失或明显减弱。
2. 原图文件仍在，资讯库缩略图仍是原图。
3. 未配视觉模型时成片行为与现在一致。
4. 手动画框去水印仍可用。
5. GIF 入选时成片仍能动，只是不洗。
