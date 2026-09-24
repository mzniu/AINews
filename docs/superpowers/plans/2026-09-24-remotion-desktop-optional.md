# 桌面可选 Remotion 成片引擎 — Implementation Plan

> **For agentic workers:** Use `executing-plans` or implement task-by-task. Checkboxes track progress.  
> **Spec:** `docs/superpowers/specs/2026-09-24-remotion-desktop-optional-design.md` v1.1  
> **Prerequisite:** P1 开工前完成 Spec §10.3 调研 R1–R4（可单独 PR 文档+spike）。

**Goal:** 桌面用户可在系统配置中查看成片引擎状态、选择 auto/remotion/python；P1 一键安装 Remotion 运行时；出片路径可观测且与配置一致。

**Architecture:** 用户意图在 `desktop_runtime.local.yaml`；机器状态在 `data/runtime/remotion_v1.json`；`resolve_video_renderer()` 统一决策；下载与 PATH 注入仅在 Tauri；Python 只读状态并渲染。

**Tech Stack:** FastAPI, PyYAML, pytest, Tauri 2, settings 静态页, 现有 `video_render_service` / `remotion_render_service`.

## Global Constraints

- CI **禁止**真 `npm install` / 真 Remotion render（mock 或 skip）
- 不删除 Python 渲染路径
- `VIDEO_RENDERER` env 优先级高于 yaml（§5）
- packaged 默认 `preferred=auto`（无 yaml 时）
- 环境变量统一 `AINEWS_NODE_HOME`（非 `AINES_*`）
- 未得到用户要求时不 git commit
- 构建检查：`remotion/package-lock.json` 必须在 app bundle 内

## File Map

| 动作 | 路径 |
|------|------|
| Create | `services/ingestion/video_renderer_config.py` — 读 yaml、算 `active`、升级检测 |
| Create | `api/routes/runtime_routes.py` — GET/PUT `/api/runtime/video-renderer` |
| Create | `tests/test_video_renderer_config.py` |
| Create | `tests/test_runtime_video_renderer_api.py` |
| Create | `static/js/settings_video_renderer.js` |
| Create | `desktop/remotion-runtime-manifest.json` — P1 Node zip pin + sha256 |
| Create | `desktop/src-tauri/src/remotion_setup.rs` — P1 |
| Modify | `services/ingestion/remotion_render_service.py` — `remotion_project_dir`, 显式 npx, 探测 |
| Modify | `services/ingestion/video_render_service.py` — 矩阵 + fallback 开关 + renderer 元数据 |
| Modify | `services/ingestion/media_pipeline.py` — steps.renderer |
| Modify | `src/app_version.py` — 供 lock 升级对比（已有则复用） |
| Modify | `desktop/src-tauri/src/backend.rs` — 注入 `AINEWS_APP_VERSION`（已有）+ P1 `AINEWS_NODE_HOME` |
| Modify | `desktop/src-tauri/src/lib.rs` — 注册 remotion 命令 |
| Modify | `desktop/scripts/build-release-fast.ps1` — assert remotion lock 在 bundle |
| Modify | `static/settings.html` — Tab + panel |
| Modify | `static/js/settings_render_templates.js` 或 inline — P0 顶栏 active 提示 |
| Modify | `web_server.py` 或路由聚合 — mount runtime_routes |
| Modify | `.gitignore` — `config/desktop_runtime.local.yaml` |
| Modify | `README.md` — 桌面成片引擎一节 |

---

## Phase 0 — 配置、API、行为矩阵、可观测（约 1–2 周）

### Task 0.1: P1 调研 R1–R4（可与开发并行，P1 编码前必须收口）

- [ ] **R1** 文档：Remotion browser vs Playwright Chromium（`docs/superpowers/specs/` 或 plan 附录）
- [ ] **R2** 选定 npm 镜像 / offline cache 策略
- [ ] **R3** 验证 `build-release-fast` 拷贝后 `bundle-resources/app/remotion/package-lock.json` 存在
- [ ] **R4** Windows 子进程显式 `npx.cmd` spike（结论写入 spec 或 plan）

---

### Task 1: `video_renderer_config` 模块

**Files:** Create `services/ingestion/video_renderer_config.py`, `tests/test_video_renderer_config.py`

**Interfaces:**

- `load_desktop_runtime_config() -> dict`
- `save_desktop_runtime_config(patch) -> dict`
- `remotion_marker() -> dict | None`（读 `get_data_dir()/runtime/remotion_v1.json`）
- `compute_active_renderer(preferred, allow_fallback, remotion_ready, env_override) -> tuple[str, str | None]`
- `check_upgrade_required(marker, app_version, lock_path) -> bool`

- [ ] **Step 1:** 单测矩阵覆盖 §6（至少 8 cases）
- [ ] **Step 2:** 实现模块
- [ ] **Step 3:** `pytest tests/test_video_renderer_config.py -v`

---

### Task 2: 扩展 `resolve_video_renderer` 与 `render_ingested_video`

**Files:** Modify `video_render_service.py`, extend `tests/test_video_render_service.py`

- [ ] **Step 1:** 单测：`packaged` mock 默认 `auto`；`allow_python_fallback=false` + not ready → 错误 dict
- [ ] **Step 2:** `resolve_video_renderer` 读 yaml；env 优先
- [ ] **Step 3:** `render_ingested_video` 返回增加 `renderer`, `fallback_from`；`preferred=remotion` 未就绪且 no fallback → 不调用 Python
- [ ] **Step 4:** Remotion 失败 + fallback false → 不 fallback
- [ ] **Step 5:** `pytest tests/test_video_render_service.py -v`

---

### Task 3: `remotion_project_dir`（P0 最小）

**Files:** Modify `remotion_render_service.py`, `tests/test_remotion_render_service.py`

- [ ] **Step 1:** 抽出 `remotion_project_dir()`；`remotion_available()` 用该路径
- [ ] **Step 2:** 单测：`REMOTION_PROJECT_DIR` env 覆盖
- [ ] **Step 3:** `pytest tests/test_remotion_render_service.py -v`

---

### Task 4: HTTP API

**Files:** Create `api/routes/runtime_routes.py`, register in app

- [ ] **Step 1:** `GET` 返回 spec §13 字段（`last_render_renderer` 可先 null）
- [ ] **Step 2:** `PUT` 写 yaml
- [ ] **Step 3:** `tests/test_runtime_video_renderer_api.py` TestClient

---

### Task 5: `media_pipeline` 可观测性

**Files:** Modify `media_pipeline.py`, one pipeline test

- [ ] **Step 1:** `steps["render_video"]["renderer"]` 来自 `render_ingested_video` 返回值
- [ ] **Step 2:** 断言现有 `test_media_pipeline_*` 或新增最小用例

---

### Task 6: 设置页 P0（无下载按钮）

**Files:** `settings.html`, `settings_video_renderer.js`, bump `settings_tabs.js` if needed

- [ ] **Step 1:** Tab「成片引擎」+ panel
- [ ] **Step 2:** 加载 GET API；保存 PUT；展示 `active` / `consistent` / `repair_hint`
- [ ] **Step 3:** 非 Tauri 隐藏安装区块 C；Tauri 显示「即将支持一键安装（P1）」或禁用按钮
- [ ] **Step 4:** `allow_python_fallback` 复选框与 §6 一致

---

### Task 7: 成片模板 Tab 提示

**Files:** `settings_render_templates.js` 或 `settings.html` panel-render-templates

- [ ] **Step 1:** 顶栏拉 `GET /api/runtime/video-renderer` 显示 `active` + 链接

---

### Task 8: 文档与 gitignore

- [ ] **Step 1:** `.gitignore` 增加 `config/desktop_runtime.local.yaml`
- [ ] **Step 2:** `README.md` 桌面成片引擎 + 与 Web 开发差异

**P0 验收:** 设置页可用；矩阵单测绿；pipeline steps 含 renderer；未装 Remotion 时 `active=python`。

---

## Phase 1 — Tauri 安装 + 探测 + 设置页安装（约 3–5 周，依赖 Task 0.1）

### Task 9: `remotion-runtime-manifest.json` + 构建检查

- [ ] Node LTS win x64 URL、version、sha256
- [ ] `build-release-fast.ps1` 末尾 assert `remotion/package-lock.json` in `AppDst`

---

### Task 10: `remotion_setup.rs`

**Files:** Create `desktop/src-tauri/src/remotion_setup.rs`, wire `commands.rs`, `lib.rs`

- [ ] 下载 zip → 校验 sha → 解压 `data/runtime/node/`
- [ ] 同步 `app_dir/remotion` → `remotion-project/`
- [ ] `npm ci`（子进程，日志 `remotion_setup.log`，进度事件）
- [ ] `browser ensure`
- [ ] 写 `remotion_v1.json`（含 `app_version`, `lock_sha256`）
- [ ] `SETUP_LOCK` 防并发（同 `runtime_setup`）

---

### Task 11: `spawn_backend` 注入

**Files:** `backend.rs`, `lib.rs`（读 marker，设置 `AINEWS_NODE_HOME`, `REMOTION_PROJECT_DIR`, PATH）

- [ ] 仅当 marker 完整且 `upgrade_required=false` 时注入

---

### Task 12: 探测与 `remotion_available` 升级

**Files:** `remotion_render_service.py`

- [ ] `probe_remotion_runtime()` → 更新 marker 缓存时间戳
- [ ] `render_with_remotion` 显式 npx 路径
- [ ] `upgrade_required` 在 GET API 反映

---

### Task 13: 设置页 P1

**Files:** `settings_video_renderer.js`

- [ ] 「下载并配置 Remotion」→ `invoke('remotion_setup_run')`
- [ ] 监听 `ainews:remotion-setup-progress`
- [ ] 磁盘占用（可选 `du` 或目录大小估算）
- [ ] `upgrade_required` 时强调「重新安装」

---

### Task 14: 手动验收清单（非 CI）

- [ ] 干净 Windows 桌面包：安装 Remotion → 出片日志 `renderer=remotion`
- [ ] 升级到新版 app（lock 变）→ `upgrade_required` → 重装后恢复
- [ ] 关 fallback + preferred remotion + 无安装 → 出片失败有明确错误

**P1 验收:** Spec §17 P1 条款。

---

## Phase 2 — 体验与运维（ backlog）

- [ ] CDN 预构建 `node_modules` tarball（按 `app_version` + lock sha）
- [ ] `GET /api/runtime/summary` 聚合 Playwright + Remotion + ML
- [ ] 首次自动出片 toast 引导设置页（`active=python` && user never dismissed）
- [ ] 试渲染 1 帧自检
- [ ] 「清除 Remotion 运行时」按钮
- [ ] macOS 桌面包（若启动）复用 manifest 结构

---

## 建议实施顺序（单人/单 agent）

```text
0.1 调研 R1–R4（可与下并行）
1 → 2 → 3 → 4 → 5 → 6 → 7 → 8   # P0 可发布
9 → 10 → 11 → 12 → 13 → 14      # P1
```

## 预估

| 阶段 | 工程人天（粗估） |
|------|------------------|
| P0 | 3–5 |
| P1 调研 | 2–3 |
| P1 实现 | 8–12 |
| P2 | 按需 |

---

## 与当前未提交代码的关系

- 已做的 Python `fit_rgba_within_box` 与 Remotion 路线 **互补**（Python 回退质量）；P0 不必改 Remotion。
- `src/app_version.py` / 桌面 `AINEWS_APP_VERSION` 直接用于 marker 升级检测。
