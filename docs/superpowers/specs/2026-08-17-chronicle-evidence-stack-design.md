# 小牛聊AI证据卡模板设计

> 日期：2026-08-17  
> 状态：已批准实施  
> 范围：新增第三条内置成片模板；沿用 `chronicle_frame` 渲染器；不替换现有档案模板

参考构图（用户提供的竖屏证据图）：先品牌/空顶 → 白卡物证 → 大标题在卡下 → 彩色评论摘要。  
品牌仍用小牛聊AI 科技蓝，不仿参考图的纯黑底与品红摘要。

---

## 1. 目标

增加一套「先证据、再命名」的竖屏模板，适合需要把配图当物证的快讯。

已确认决策：

1. **大标题在白卡下方**（与现有档案模板相反）。
2. **顶部只留品牌**（牛标 / 小牛聊AI / 口号 / RECORD），品牌下直接白卡，不再放引语或网友锐评。
3. **实现方式 B**：沿用 `layout_kind: chronicle_frame`，用 YAML 开关切换标题区域；新建内置模板，不改档案模板。
4. **不改系统默认模板**。设置页会出现新模板，需手动选用或之后再设默认。
5. **不新增 LLM 字段**。仍用 `main_line1` / `main_line2` / `sub_title` / `sub_title2` / `summary`。

成功标准：

- 选新模板出片：品牌 → 白卡 → 标题（左侧青竖条）→ 摘要（浅青灰）→「AI 快讯」。
- 选档案模板出片：观感与现在一致（标题仍在卡上）。
- 封面仍不画摘要。
- 运镜继续用现有 `card_motion`。

---

## 2. 非目标

- 新 `layout_kind`
- 通用任意拖拽排版引擎
- 卡内黄高亮 / 红字编号 / 邮件批注（那是参考图编辑痕迹，不是模板能力）
- 改自动出片默认模板
- 改口播或标签生成
- 已出成片自动重渲

---

## 3. 画面结构（1080×1920）

百分比相对画布高度，写入新模板 `layout`，可微调：

```
┌─ 科技蓝底 + 外框 ─────────────────────────────────┐
│  [牛] 小牛聊AI              RECORD {年}            │
│      粉碎AI信息差 / 消除AI焦虑                      │
│                                                    │
│     ┌──────── 白卡证据窗 ─────────┐                │
│     │  入选配图（封面 1 张；视频逐张 + 运镜）│        │
│     └────────────────────────────┘                │
│                                                    │
│  |  main_line1                                     │
│  |  main_line2 / sub_title / sub_title2            │
│                                                    │
│  ────────                                          │
│  summary（浅青灰评论腔，最多 3 行）                 │
│  |  AI 快讯                                        │
└────────────────────────────────────────────────────┘
```

| 元素 | 约略位置 | 来源 |
|------|----------|------|
| 品牌顶栏 | 现有 chrome，约 4%–16% | 模板 `chrome` |
| 白卡 | 水平 8%–92%，垂直 **18%–52%** | 入选图 |
| 标题块 | **55%** 起，左对齐；左侧青色竖条 | `main_line1/2`、`sub_title/2` |
| 摘要 | **75%** 起，最多 3 行 | `summary`；封面不画 |
| 页脚 | 现有 `footer_y_percent` | `chrome.footer_left` |

竖条颜色用 `palette.accent`（`#3DDCFF`），对应参考图紫蓝条，改成品牌青。

摘要颜色用新字段 `typography.summary_color`（默认 `#9EC9D8`），与主标题白字分开：上面是判断，下面是评论。高亮词仍可用 `title_highlight_color` / footer highlight。

---

## 4. 模板 YAML

新内置项：

```yaml
- id: chronicle_evidence_stack
  label: 小牛聊AI证据卡
  builtin: true
  layout_kind: chronicle_frame
  # palette / chrome / video.card_motion 从档案模板复制
  layout:
    title_placement: below_card   # 档案模板缺省 = above_card
    card_top_percent: 18
    card_bottom_percent: 52
    card_left_percent: 8
    card_right_percent: 92
    card_inset_px: 16
    title_top_percent: 55
    title_rule: true
    title_rule_width_px: 4
  typography:
    summary_y_percent: 75.0
    summary_color: "#9EC9D8"
    footer_y_percent: 85.2
```

`chronicle_archive_tech_blue` 不写 `title_placement`（或显式 `above_card`），行为不变。

---

## 5. 渲染改动

文件：`services/ingestion/chronicle_render.py`

- `_card_box` / `hero_inner_box` 已读 `layout` 百分比，新模板只需换数字。
- `render_chronicle_frame`：
  - `title_placement == below_card` 时，标题块改到白卡之后画，Y 用 `title_top_percent`。
  - `title_rule: true` 时在标题块左侧画一条 `accent` 竖线（高度约等于标题行总高）。
  - 摘要 fill 优先 `typography.summary_color`，否则仍用 `palette.text`。
- `render_chronicle_cover`：继续 `include_summary=False`；卡下标题仍画（封面也要看到钩子）。
- `render_chronicle_video`：不改运镜选择逻辑，白卡位置随 layout 走。

未知 `title_placement` 按 `above_card` 处理，不报错。

---

## 6. 产品入口

- 设置 → 成片模板列表自动出现「小牛聊AI证据卡」（builtin，可改 chrome/色板，不可删）。
- 设为默认后，自动出片才走这套。
- 资讯库「重新出片」可当次选该模板（现有 `template_id` 通道）。

---

## 7. 测试

- YAML 能加载 `chronicle_evidence_stack`；`layout_kind` 合法。
- 证据卡：标题文字的 Y ≥ 白卡底边；档案模板标题 Y < 白卡顶边。
- `title_rule: true` 时标题左侧有 accent 色竖条像素。
- 摘要使用 `summary_color`，不是纯白。
- 封面不包含摘要正文。
- 档案模板回归：现有 `test_chronicle_render.py` 仍过。

---

## 8. 风险

- **标题过长**：卡下可用高度约 17%。超长仍按现有换行上限（主标题最多 2 行，副标题各 1 行），不向白卡回挤。
- **白卡与标题间距**：18–52 与 55 之间留约 3% 空隙；太挤只改 YAML。
- **参考图里的批注高亮**：本轮不做自动标注。
