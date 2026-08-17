# 成片模板（视频 + 封面绑定）设计

> 日期：2026-08-13
> 状态：已批准实施（含 UX P0）
> 范围：把现有成片/封面设定收成可配置模板；内置两套；自动出片走系统默认；手动生成可选模板

参考图（金色原版，实施时改为科技蓝）：
`docs/superpowers/specs/assets/2026-08-13-chronicle-archive-gold-reference.png`

---

## 1. 目标

运营可以维护多套「成片模板」。每一套同时决定**封面**和**视频**的画布、配色、排版与时长策略。

已确认决策：

1. **视频和封面绑成一套模板**，生成时只选一次。
2. **自动出片只用系统默认模板**；默认模板可在配置页更换。
3. **第一套** = 把当前线上设定原样沉淀。
4. **第二套** = 参考图的「档案框」布局，按本产品改成科技蓝，不仿造微博帖。

成功标准：

- 默认仍是第一套时，自动出片观感与现在一致（回归测试）。
- 把默认改成第二套后，新自动出片全部走档案框 + 科技蓝，无需改代码。
- 主页「生成视频」和下次「重新出片」可以选择非默认模板；当次覆盖（BGM / 背景）不写回模板。

---

## 2. 非目标（本轮不做）

- 封面模板与视频模板拆成两个实体
- 自动流水线按单篇文章选模板
- 可视化拖拽排版器
- 按模板切换 LLM 文案提示词（继续用现有 `generate_video_content`）
- 第二套上叠加 `gold_sparkle` / `snowfall` 等粒子特效
- 修改评分门槛、自动发布、配图评估

---

## 3. 两套内置模板

### 3.1 `flash_news_portrait` — 快讯竖屏（默认）

`layout_kind: classic_overlay`

把现在散落的默认值收进来，行为不变：

| 项 | 现值 |
|----|------|
| 画布 | 1080×1440，24fps |
| 背景 | `static/imgs/bg.png` |
| 主标题 | 72px 白，约在画面高度 12% |
| 副标题 | 68px |
| 封面 | 同画布；不画滚动摘要 |
| 视频 | 显示摘要，`line_uniform` 滚动 |
| 选图 | 最多 4 张 |
| 时长 | 2 张 `[3.5, 3.5]`；3 张 `[2.5, 3.0, 3.0]`；≥4 张每张 2.0s |
| BGM | `static/music` 随机 |
| 封面片头 | 前置 1.0s |

图片仍是全幅 Ken Burns，标题叠在上方——现有 `_render_frame_animated`。

### 3.2 `chronicle_archive_tech_blue` — 小牛聊AI档案（科技蓝）

`layout_kind: chronicle_frame`

结构对齐参考图，按本产品改三处：

1. **配色**：全部金色/琥珀色改为科技蓝（见 3.3）。
2. **中间卡不是假社交帖**：不画头像、Follow、微博正文、来源名。白卡片是「证据夹」，只放 **一个关键词** + 入选配图。
3. **文案仍用现有草稿字段**：`main_line1/2`、`sub_title/2`、`summary`、`highlight_keywords`、`tags`，不另写一套生成。

画布：**1080×1920**（9:16）。档案框需要页眉 + 标题 + 卡片 + 页脚的纵向节奏；压进 3:4 会挤掉卡片。

其余成片参数与第一套对齐，避免两套运营习惯分叉：最多 4 张入选图、`static/music` 随机 BGM、封面片头 1.0s。视频摘要改由页脚承担，故 `show_summary: false`（不再全屏滚摘要）。

默认模板仍是第一套（3:4），现有多平台发布不受影响。只有把默认改成第二套、或手动选第二套时，才会出 9:16。

### 3.3 科技蓝色板

| Token | 色值 | 用途 |
|-------|------|------|
| `bg` | `#070B10` | 底色 |
| `bg_glow` | `#0E2A44` | 中心圆形水印的淡蓝辉光 |
| `accent` | `#3DDCFF` | 描边、角标、竖线、高亮字、RECORD 框 |
| `accent_dim` | `#1A6A8A` | 弱描边、刻度 |
| `text` | `#F4F7FA` | 主标题、页脚正文 |
| `text_muted` | `#8B96A8` | 英文眉题、CHRONICLE ARCHIVE |
| `card` | `#FFFFFF` | 证据卡 |
| `card_tab` | `#070B10` | 卡片左上标签底 |
| `frame` | `#3DDCFF` | 外框与四角方块，线宽 1–2px |

参考图里「点火弹灰还能给朋友派烟」那种强调行，用 `accent` 而不是金。

### 3.4 档案框分区（第二套）

从上到下，均为模板可改文案，实施时按百分比定位（见附录几何）：

```
┌─ 外框 + 四角方块 ─────────────────────────────────┐
│  [牛] 小牛聊AI        RECORD {年}                  │
│      CHRONICLE ARCHIVE / VERIFIED FILE             │
│  AI CHRONICLE / ARCHIVE RECORD                     │
│  |  主标题（main_line1，可加 main_line2）            │
│  |  副标题白（sub_title）                           │
│  |  副标题强调青（sub_title2，流量钩子）             │
│                                                    │
│     ┌ EVIDENCE DOSSIER / VERIFIED SOURCE ┐         │
│     │  关键词（如 大模型）                   │         │
│     │  入选配图（封面 1–2 张；视频逐张切换） │         │
│     └────────────────────────────────────┘         │
│                                                    │
│  |  {年}                                           │
│  |  快讯档案                                       │
│         页脚摘要（summary，高亮词用 accent）         │
└────────────────────────────────────────────────────┘
```

字段映射：

| 画面位置 | 数据来源 |
|----------|----------|
| Logo「牛」、品牌名「小牛聊AI」、英文眉题、卡片标签、页脚左栏「快讯档案」 | 模板 `chrome`（可编辑） |
| `RECORD {年}`、页脚 `{年}` | `article.published_at` 的年；缺失则用北京时间当前年 |
| 主标题 | `draft.main_line1` + 可选 `main_line2` |
| 副标题白 / 青 | `draft.sub_title` / `draft.sub_title2` |
| 卡片关键词 | 见下方选取规则；**不使用**来源名 |
| 卡片内图片 | 流水线已选图片 |
| 页脚 | `draft.summary`；`highlight_keywords` 着 `accent` |
| 页脚前缀 | 模板可配 `footer_strip_prefixes: ["小牛说："]`，只影响绘制，不改草稿 |

卡片只画 **一个** 关键词，去 `#`，最多 8 个汉字当量，超长截断。选取顺序（命中即停，不调 LLM）：

1. `draft.tags` 里第一个不在跳过表的标签。跳过：`小牛说` / `小牛说AI` / `小牛聊AI`，以及泛词 `人工智能` / `AI资讯` / `AI应用` / `科技前沿` / `行业观察` / `技术趋势` / `AI`。
2. 否则 `article.keywords_json` 第一项（同样跳过泛词）。
3. 否则 `draft.highlight_keywords` 第一项。
4. 否则 `article.theme`（泛词则跳过）。
5. 否则模板兜底 `chrome.card_keyword_fallback`（默认「快讯」）。

关键词画在白卡顶部，单行深色字，无头像、无 Follow。封面和视频同一关键词。封面不画英文 `EVIDENCE DOSSIER` 长标签；关键词芯片即卡签。

视频与封面共用同一套 chrome，但 **画幅不同**：

- **视频**：1080×1920 全幅；页脚摘要只出现在视频里。
- **封面**：取画布 **顶部** 1080×1440（`cover.crop: top`，禁止居中裁）。窗内只保留牛标、主标题（+ 一行钩子 `sub_title2`）、白卡。
- **封面主图**：只放 1 张评分最高的图铺满白卡（不要并排两张）。
- **视频配图**：chrome 冻结；每个 clip 只换卡内那张图，轻微 Ken Burns（缩放 ≤1.04）。
- 封面片头 1.5s。

青色 `accent` 只用于钩子行（`sub_title2`）与最多 1–2 处摘要高亮。外框/角标用 `accent_dim` 弱线，避免满屏发光。

### 3.5 品牌与素材

成片页眉品牌用 **小牛聊AI / 牛**，与站内后台名 AINews 分开。口播/摘要仍是现有「小牛说」草稿。

新建目录 `static/imgs/templates/chronicle_tech_blue/`：

| 文件 | 作用 |
|------|------|
| `bg.png` | 1080×1920 深底 + 淡蓝圆形水印（罗盘/雷达，低对比） |
| `mark_niu.png` | 「牛」字方标（青框白字），页眉左侧 |

外框、竖线、角标、RECORD 盒、卡片与标签用代码按色板绘制，避免把可变文案烤进 PNG。

---

## 4. 数据模型

### 4.1 存储

与配图评分同一套路：

- `config/render_templates.yaml` — Git 内置两套 + `default_template_id`
- `config/render_templates.local.yaml` — 用户改默认、改 chrome、新增/复制模板；`.gitignore`

合并：按 `id` 合并；local 可覆盖字段、可新增；`default_template_id` 以 local 为准（若有）。

### 4.2 模板结构

```yaml
version: 1
default_template_id: flash_news_portrait
templates:
  - id: flash_news_portrait
    label: 快讯竖屏（默认）
    builtin: true
    layout_kind: classic_overlay
    canvas: { width: 1080, height: 1440, fps: 24 }
    background_image: static/imgs/bg.png
    typography: { ... }
    video: { show_summary: true, summary_scroll_mode: line_uniform, ... }
    cover: { enabled: true }
  - id: chronicle_archive_tech_blue
    label: 小牛聊AI档案（科技蓝）
    builtin: true
    layout_kind: chronicle_frame
    canvas: { width: 1080, height: 1920, fps: 24 }
    background_image: static/imgs/templates/chronicle_tech_blue/bg.png
    palette: { accent: "#3DDCFF", ... }
    chrome: { brand: "小牛聊AI", mark_glyph: "牛", mark_path: "...", card_keyword_fallback: "快讯" }
    typography: { ... }
    video: { show_summary: false, card_ken_burns: true, cover_intro_duration_sec: 1.5, ... }
    cover: { enabled: true, width: 1080, height: 1440, crop: top, card_images: 1 }
```

`layout_kind` 是渲染分支，不是可选皮肤。未知 kind 拒绝渲染，不静默回退。

`builtin: true` 的模板：可改、可复制，**不可删除**。复制得到的新 id 可删。

### 4.3 流水线只保留「用哪套」

`article_scoring.yaml` 的 `media_pipeline` 删除（或一轮后忽略）这些视觉字段：

`background_image`、`clip_duration_sec`、`cover_width`、`cover_height`

改为：

```yaml
media_pipeline:
  render_template_id: null   # null = 系统 default_template_id
```

时长、背景、封面尺寸一律来自选中模板。`max_selected_images`、`random_bgm`、`bgm_dir`、`render_cover`、`prepend_cover_intro` 迁进模板的 `video`/`cover`；流水线 YAML 只留触发门槛与步骤开关。

兼容：若 local 仍带旧字段且未配模板，启动时把旧值写进对 `flash_news_portrait` 的覆盖，打一次性 warning。

### 4.4 出片记录

每次成功出片在 `video_prep_status_json`（或并列字段）记下：

- `render_template_id`
- `layout_kind`
- `canvas` 宽高
- 当时 `default_template_id`（便于对照「后来改了默认」）

不另建模板版本表。

---

## 5. 渲染架构

```
template_id（显式 或 default）
  → load_render_template()
  → 合并当次覆盖（主页 BGM/背景/字体/show_summary）
  → RenderSpec
  → layout_kind 分支
       classic_overlay  → 现有 _render_frame_animated
       chronicle_frame  → 新 compositor（封面一帧 / 视频逐 clip）
```

`RenderSpec` 是封面服务与视频服务的唯一输入。`render_article_cover` / `render_ingested_video` / 主页 `_create_animated_video_blocking` 都先解析 spec，不再各自读 YAML 散字段。

主页请求增加可选 `template_id`。缺省 = 系统默认。请求里的字体/颜色/背景视为当次覆盖。

资讯库「重新出片」同样可带 `template_id`；不传则用默认。自动 worker **忽略**任何按文章覆盖，始终 `default_template_id`。

---

## 6. 默认模板怎么配

唯一开关：`default_template_id`（local 可改）。

| 入口 | 行为 |
|------|------|
| 系统配置 → 成片模板 →「设为默认」 | 写 local |
| 自动出片 / 定时 worker | 只用 default |
| 主页生成视频 | 下拉，默认选中 default，可改当次 |
| 资讯库重新出片 / 重做封面 | 同上 |

同一时刻只有一个默认。设新默认会清掉旧标记。

---

## 7. API 与 UI

### 7.1 API

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/api/ingestion/render-templates` | 列表 + `default_template_id` |
| GET | `/api/ingestion/render-templates/{id}` | 详情（含 chrome/palette） |
| PUT | `/api/ingestion/render-templates/{id}` | 保存编辑（builtin 也可改字段） |
| POST | `/api/ingestion/render-templates` | 新建（通常从复制） |
| POST | `/api/ingestion/render-templates/{id}/duplicate` | 复制 |
| DELETE | `/api/ingestion/render-templates/{id}` | 仅非 builtin |
| PUT | `/api/ingestion/render-templates/default` | `{ "template_id": "..." }` |
| POST | `/api/ingestion/render-templates/{id}/preview-cover` | 用占位图出一张封面预览（可选，阶段 4） |

主页 `CreateAnimatedVideoRequest` 与资讯库 retry body 增加 `template_id: Optional[str]`。

### 7.2 系统配置 Tab

新增 **成片模板**（`/settings#render-templates`），模式对齐配图评分：

- 左：模板列表、默认标记、复制、删除（非内置）
- 右：画布、背景、色板、chrome 文案、时长表、封面开关
- 「设为默认」「保存」

主页不下沉完整编辑器，只做模板下拉。

---

## 8. 测试

- 加载/合并 yaml；local 覆盖 default
- builtin 不可删；设默认
- `classic_overlay` 从模板解析出的时长表 = 现有 `resolve_ingested_clip_durations`
- `chronicle_frame`：色板替换后画面中不得出现参考金 `#E8C547` 一类色；卡片不包含 Follow、不包含来源 `display_name`；卡面关键词按选取规则去 `#` 且只有一词
- 流水线未传 `template_id` 时使用 default
- 旧 `media_pipeline.background_image` 兼容一轮
- 封面与视频读取同一 `RenderSpec.canvas`

视觉回归：对两套各渲染一张固定文案/固定图的封面 fixture，断言尺寸与关键像素（外框 accent、卡片为白）。

---

## 9. 实施顺序

1. **模型 + 加载器 + 第一套内置**；流水线改读模板；默认仍是第一套 → 行为对齐现网。
2. **配置页 CRUD + 设默认**。
3. **第二套 compositor + 素材**；主页/重新出片下拉。
4. （可选）封面预览 API、从主页参数「另存为模板」。

阶段 1 可单独上线。阶段 3 才引入 9:16 与档案框。

---

## 10. 风险

- **第二套改默认后全是 9:16**：小红书/视频号可能裁切。缓解：默认保持第一套；配置页注明画幅。
- **标题过长撑破档案框**：沿用现有字数约束（主标题 9–12 字、副标题 11–15 字），超长截断并缩小字号一档。
- **只有 1 张入选图**：视频流水线仍要求 ≥2 张才能成片；封面仍可出。档案框封面在仅 1 张时单图铺卡。

---

## 附录 A. 档案框几何（1080×1920，可微调）

百分比相对画布：

| 元素 | 约略位置 |
|------|----------|
| 外框 inset | 2.4% |
| 页眉 | 顶部 3.5%–9% |
| 标题块 | 11%–28%，左侧竖线 x=4.5% |
| 证据卡 | 水平 8%–92%，垂直 32%–68%，圆角 12px |
| 卡片标签 | 叠在卡片顶边左上 |
| 页脚摘要 | 72%–90%，居中，最多 3 行 |
| 页脚左栏年/快讯档案 | 左 4.5%，垂直 78%–88% |

实施时用这些百分比写死在第二套模板的 `layout` 段，配置页阶段 2 只开放色板与 chrome 文案，不开放任意拖拽。

## 附录 B. 从参考图改掉的清单

| 参考图 | 本产品 |
|--------|--------|
| 金/琥珀描边与高亮 | 科技蓝 `#3DDCFF` |
| 中间微博式帖（头像 / Follow / 长文 / @账号） | 白卡 + **一个关键词** + 入选配图 |
| 页眉「AI纪年 / 纪」 | **小牛聊AI / 牛** |
| 「样本点」 | 「快讯档案」 |
| 卡片内两张 App 截图 | 流水线选中的新闻配图 |
| 金色强调副标题 | `sub_title2` 用 accent |
| 页脚三行金句 | 现有 `summary` + 高亮词 |
