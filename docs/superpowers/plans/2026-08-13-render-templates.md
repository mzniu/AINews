# 成片模板 Implementation Plan

> **For agentic workers:** Execute inline with TDD in this session. Tasks are tightly coupled (loader → pipeline → compositor → UI). Do not commit unless the user asks.

**Goal:** 把现有成片/封面设定收成可配置模板；默认第一套行为与现网一致；第二套为科技蓝档案框（封面顶部 3:4 安全窗）。

**Architecture:** YAML 内置 + local 覆盖；`get_render_template(id|None)` 解析 `RenderSpec`；流水线/封面/视频只吃 spec。`classic_overlay` 走现有渲染；`chronicle_frame` 走新 compositor。

**Tech Stack:** Python, PyYAML, Pillow, FastAPI, pytest, 现有 MoviePy 出片。

## Global Constraints

- 自动出片只用 `default_template_id`；默认可在配置页改
- 第一套画布 1080×1440，时长表与现网一致（2→[3.5,3.5]，3→[2.5,3.0,3.0]，≥4→每张 2.0）
- 第二套视频 1080×1920，封面顶部裁 1080×1440；封面单主图；页眉「小牛聊AI / 牛」
- 白卡一个关键词，不放来源名；跳过泛词
- builtin 模板不可删；未知 `layout_kind` 拒绝渲染
- 不提交 `config/render_templates.local.yaml`
- 用户未要求则不 git commit

---

### Task 1: Template loader

**Files:**
- Create: `config/render_templates.yaml`
- Create: `services/ingestion/render_templates.py`
- Test: `tests/test_render_templates.py`
- Modify: `.gitignore`

### Task 2: Card keyword picker

**Files:**
- Create: `services/ingestion/render_keyword.py`
- Test: `tests/test_render_keyword.py`

### Task 3: Clip durations + pipeline wiring (no visual regression)

**Files:**
- Modify: `services/ingestion/video_render_service.py`
- Modify: `services/ingestion/media_pipeline_trigger.py`
- Modify: `services/ingestion/media_pipeline.py`
- Modify: `services/ingestion/cover_retry.py`
- Modify: `services/ingestion/cover_render_service.py`
- Test: `tests/test_video_render_service.py` (keep existing assertions)
- Test: `tests/test_media_pipeline_trigger.py`

### Task 4: API

**Files:**
- Modify: `api/routes/ingestion_routes.py`
- Test: `tests/test_render_templates_api.py`

### Task 5: Chronicle compositor

**Files:**
- Create: `services/ingestion/chronicle_render.py`
- Test: `tests/test_chronicle_render.py`
- Modify: cover + ingested video to branch on `layout_kind`

### Task 6: Settings + generate-time picker

**Files:**
- Modify: `static/settings.html`, `static/js/settings_tabs.js`
- Create: `static/js/settings_render_templates.js`
- Modify: `static/js/ingestion_library.js`, `static/js/index/main.js` (template_id)
