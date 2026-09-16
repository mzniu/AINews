# 纪年模板摘要打字机效果设计

> 日期：2026-09-15  
> 状态：已实施  
> 范围：`layout_kind: chronicle_frame` 成片视频页脚摘要；封面不变

---

## 1. 目标

纪年模板（小牛聊AI档案、小牛聊AI证据卡）的视频页脚摘要，从**静态一次性显示**改为**打字机逐字出现**，增强阅读节奏与科技感。

已确认决策：

1. **作用范围**：整片视频**只打一次**——从第一个配图 clip 开始打字，**可跨 clip 延续**；打满后所有后续 clip 保持满字，**不重播、不重头**。
2. **封面不画摘要**（与现有 `include_summary=False` 一致）。
3. **实现方式**：沿用 `chronicle_frame` compositor，在 `make_frame(t)` 路径按**视频全局时间**绘制部分摘要；不引入 MoviePy TextClip。
4. **默认行为**：新字段默认 `mode: static`，避免已上线模板观感突变（见 §7）。
5. **两套纪年模板共用同一套动画逻辑**，仅 YAML 排版/配色不同。

成功标准：

- 选纪年模板、开启 `typewriter` 出片：摘要从第一段配图起逐字打出；若第一段 clip 结束时尚未打完，**下一段配图 clip 从当前进度接着打**；全文打满后直至片尾保持满字。
- `mode: static` 时观感与现在完全一致（回归测试通过）。
- 任意长度摘要，在固定语速下最终都能打满（不因单段 clip 过短而截断或瞬间补齐）。
- 封面、快讯竖屏（`classic_overlay`）不受影响。

---

## 2. 非目标

- 快讯竖屏模板的滚动摘要改造
- 标题 / 副标题打字机
- 每个配图 clip 重头打一遍
- 登录页、预览页、Web 端实时预览打字机（仅成片视频）
- 打字音效
- 用户可视化拖拽配置打字速度（本轮只 YAML + local 覆盖）

---

## 3. 视觉效果

### 3.1 动画描述

- **粒度**：按 Unicode 字符（中文、英文、数字、标点均 1 字一步）；不跳过空格。
- **顺序**：先 `_prepare_summary_lines` 换行，再按行从上到下、行内从左到右依次显示。
- **高亮**：`highlight_keywords` 仅在对应字符**已打出**时着色；未打出的字不预显。
- **光标**（可关）：在当前末尾显示 `|` 竖线，颜色 `palette.accent`；全文打满后 `cursor_hide_after_done_sec` 后隐藏。
- **跨 clip**：换图时摘要**不重置**——第二张、第三张配图 clip 继续显示已打出的字并接着打。

### 3.2 时间轴（整片视角）

设：

- `T0` = 第一个配图 clip 起点（封面片头之后）
- `global_t` = 当前帧相对成片起点的时间
- `N` = 摘要总字符数
- `cps` = `chars_per_second`（默认 14）
- `delay` = `start_delay_sec`（默认 0.35）

可见字数：

```
typing_t = max(0, global_t - T0 - delay)
visible_char_count = min(N, floor(typing_t * cps))
```

**与 clip 边界无关**——第一段 2s 只打了 28 字，第二段从第 29 字继续。

示例（4 张图，每段 2s，N=80 字，cps=14，delay=0.35）：

```
global_t   clip    摘要状态
0.35s      #1      开始打第 1 字
2.0s       #1→#2   约 23 字（换图不重置）
2.35s      #2      继续…
4.0s       #2→#3   约 51 字
6.0s       #3→#4   约 79 字
~6.1s      #4      打满 80 字，光标稍后消失
6.1s–结束           满字静止
```

### 3.3 可选：片尾前打完（`fit_video_duration`）

若开启 `fit_video_duration: true`，当 `typing_t` 接近「成片总时长 - delay - tail_margin」仍未满字时，临时提高有效 `cps`（上限 `max_chars_per_second`，默认 28），尽量在最后一个 clip 结束前打满。默认 **关闭**，使用恒定 14 字/秒。

### 3.4 与卡面动画的关系

每个 clip 内：卡面 Ken Burns / GIF 与摘要打字**并行**。chrome 层不含摘要；每帧在 hero 合成后按 `global_t` 叠摘要。换 clip 只换卡内图，摘要层按全局进度续写。

---

## 4. 配置模型

```yaml
video:
  summary_animation:
    mode: typewriter          # static | typewriter
    scope: once               # 整片一次、跨 clip 延续、不重播
    chars_per_second: 14
    start_delay_sec: 0.35
    show_cursor: true
    cursor_blink_hz: 2
    cursor_hide_after_done_sec: 0.5
    fit_video_duration: false # 可选：为在片尾前打完而加速
    max_chars_per_second: 28  # 仅 fit_video_duration 时使用
    tail_margin_sec: 0.5      # 仅 fit_video_duration：距成片结束保留满字静止时间
```

- 缺省或 `mode` 缺失 → `static`。
- 已删除「仅第一段 clip 内打完」及 `end_margin_sec`（第一段专用）逻辑。

---

## 5. 架构与数据流

### 5.1 模块边界

| 单元 | 职责 |
|------|------|
| `_prepare_summary_lines` | 不变 |
| `SummaryLayout`（新） | 缓存字体、换行、每字坐标、关键词区间 |
| `_draw_summary_partial`（新） | 按 `visible_char_count` + 光标绘制 |
| `_summary_visible_chars(global_t, …)`（新） | 由全局时间与 `cps` 算可见字数 |
| `render_chronicle_frame` | 支持 `summary_visible_chars: int \| None` |
| `build_chronicle_video_clips` | `make_frame` 接收 `clip_index`、`t` → 算 `global_t` → 叠摘要 |
| `render_chronicle_video` | 传入 `cover_intro_sec`、`durations[]`、动画配置 |

### 5.2 全局时间

```
global_t = cover_intro_sec + sum(durations[0..index-1]) + t_within_clip
visible_char_count = _summary_visible_chars(global_t, layout, anim_cfg)
```

所有 clip 共用同一 `SummaryLayout` 与同一进度函数；**clip 索引只参与算 `global_t`，不参与重置字数**。

### 5.3 渲染路径

```
render_chronicle_frame(include_summary=False)  →  chrome
        ↓
compose_chronicle_live_frame / still + hero
        ↓
_draw_summary_partial(layout, visible_char_count, global_t)
```

---

## 6. 错误与边界

| 情况 | 行为 |
|------|------|
| 摘要为空 | 不画字、不画光标 |
| 第一段 clip 很短 | 正常；下一段 clip 接着打 |
| 全文在倒数第二段打完 | 最后一段全程满字 |
| 仅 1 张图、长摘要 | 单 clip 内持续打，直至打满或片尾 |
| `fit_video_duration: true` 且摘要极长 | 加速至 `max_chars_per_second`；若仍不够，片尾 `tail_margin` 前**瞬间补齐**（仅此兜底） |
| GIF 卡面 | 支持 |

---

## 7. 默认模板策略

**保守（推荐）**：内置纪年模板 YAML 默认 `mode: static`；local 或后续设置页开启 `typewriter`。

---

## 8. 测试

1. **跨 clip 延续**：两段 clip 各 2s，`N=50, cps=14` → 第一段结束约 23 字，第二段 `global_t=2.35` 时 > 23 字且 < 第一段单独累计值。
2. **打满后静止**：`visible_char_count` 达到 `N` 后不再增加。
3. **不重播**：第三段 clip 不出现字数回退。
4. **高亮滞后**：未打出字符不着色。
5. **静态回归**：`mode: static` 与改前一致。
6. **封面**：仍无摘要。

---

## 9. 实施任务概要

1. `SummaryLayout` + `_draw_summary_partial` + `_summary_visible_chars`。
2. `render_chronicle_frame` 支持 `summary_visible_chars`。
3. `build_chronicle_video_clips` 全 clip 传 `global_t` 叠摘要（不仅第一段）。
4. `config/render_templates.yaml` 增加 `summary_animation`（默认 `static`）。
5. 测试 + 目视出片。

---

## 10. 参考

- `services/ingestion/chronicle_render.py`
- `docs/superpowers/specs/2026-08-13-render-templates-design.md`
