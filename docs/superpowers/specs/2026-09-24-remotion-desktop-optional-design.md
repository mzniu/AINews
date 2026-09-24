# 桌面可选 Remotion 成片引擎 — 设计规格 v1.1

> 日期：2026-09-24  
> 状态：v1.1 — 首席架构师 Review 已合入；待 `writing-plans` 执行  
> 实施计划：`docs/superpowers/plans/2026-09-24-remotion-desktop-optional.md`  
> 关联：  
> - `services/ingestion/video_render_service.py`  
> - `services/ingestion/remotion_render_service.py`  
> - `desktop/src-tauri/src/runtime_setup.rs`  
> - `static/settings.html`

---

## 1. 问题

- 资讯自动出片 **默认** 走 Remotion（React 模板、letterbox 与开发机一致）。
- **桌面 NSIS 包** 只捆绑 Python + FFmpeg +（可选）Playwright，**不捆绑** Node、`remotion/node_modules`、Remotion 浏览器二进制。
- 因此安装后 `remotion_available()` 几乎恒为 false，实际成片走 **Python 回退**。
- 用户希望：**首包保持小体积**，后期在 **系统配置页** 下载并配置，再启用 Remotion。

---

## 2. 目标 / 非目标

### 2.1 目标

| # | 目标 |
|---|------|
| G1 | 桌面端 **可选安装** Remotion 运行时（Node + 依赖 + 浏览器），目录在 `AINEWS_DATA_DIR`。 |
| G2 | **系统配置**「成片引擎」：状态、下载、首选渲染器、失败回退策略。 |
| G3 | 未安装或失败时 **可配置回退 Python**，不默认阻断出片。 |
| G4 | 安装完成后无需手改环境变量即可优先 Remotion。 |
| G5 | 与 **Playwright `runtime_setup`** 交互模式一致。 |
| G6 | 出片结果 **可观测**（`media_pipeline` steps 记录实际 `renderer`）。 |

### 2.2 非目标

- Remotion 打进首包 NSIS（默认）。
- Web/Linux 服务器走「下载便携 Node zip」（仍用系统 Node + `npm install`）。
- 删除 Python 渲染路径。
- P0/P1 不做 Remotion Studio 内嵌。

---

## 3. 产品路线（三期）

| 阶段 | 内容 |
|------|------|
| **P0** | 可观测 + 配置意图 + fallback 语义落地 + steps 记 renderer |
| **P1** | Tauri 下载安装 + 探测 + 升级检测 + 设置页安装 UI |
| **P2** | CDN 预构建 tarball、增量更新、试渲染自检、可选 `GET /api/runtime/summary` 聚合 |

---

## 4. 配置与状态：单一事实来源（必改）

| 数据 | 文件 | 内容 |
|------|------|------|
| **用户意图** | `config/desktop_runtime.local.yaml`（gitignore） | `preferred`、`allow_python_fallback`、可选 `npm_registry`（P1） |
| **机器状态** | `{AINEWS_DATA_DIR}/runtime/remotion_v1.json` | node 路径、`app_version`、`remotion_lock_sha256`、浏览器路径、安装步骤、最后探测时间 |

**禁止**在 yaml 里写绝对路径；路径只在 marker。

`GET /api/runtime/video-renderer` **合并**二者，并返回：

- `consistent: bool` — yaml 与 marker 是否一致（例如 marker 缺失但用户选了「始终 Remotion」）
- `repair_hint: string | null` — 如 `upgrade_required`、`install_incomplete`

---

## 5. 解析优先级与默认策略（必改）

```text
1. 环境变量 VIDEO_RENDERER=python|remotion  → 强制（运维/开发）
2. config/desktop_runtime.local.yaml
3. 默认 preferred：
     - is_packaged() == true  → auto
     - 开发仓库 / 非 packaged   → 可保持 env 默认 remotion（.env.example）
```

`resolve_video_renderer()` 实现上述链；**不再**让 packaged 桌面默认隐含 `remotion` 且无 Node。

---

## 6. 出片决策矩阵（必改）

| preferred | remotion_ready | allow_python_fallback | 行为 |
|-----------|----------------|----------------------|------|
| `python` | * | * | **Python** |
| `auto` | false | * | **Python** |
| `auto` | true | * | **Remotion**；失败见下行 |
| `remotion` | false | **true** | **Python**（等同 auto，UI 黄灯「未安装，已回退」） |
| `remotion` | false | **false** | **失败**：`render_ingested_video` 返回 `remotion_not_ready`，**不出片** |
| `remotion` | true | * | **Remotion** |
| Remotion 渲染失败 | * | **true** | **Python**（与今天一致） |
| Remotion 渲染失败 | * | **false** | 返回错误，**不出片** |

**P0 必须**实现 `allow_python_fallback`；若未实现，UI 不得提供可关闭的复选框（只读「当前恒为开启」）。

---

## 7. `remotion_available()` 与探测（必改）

「就绪」= 目录存在 **且** 探测通过（结果缓存到 marker，TTL 建议 24h 或 app 启动时强制刷新）。

探测步骤（P1，超时各 10s）：

1. `AINEWS_NODE_HOME/node.exe -v`
2. `npx.cmd remotion versions`（`cwd=remotion_project_dir()`）

P0 可仅检查 `package.json` + `node_modules` + `which node`，但 P1 必须升级为探测。

```python
def remotion_project_dir() -> Path:
    return Path(os.environ.get("REMOTION_PROJECT_DIR") or Config.ROOT_DIR / "remotion")
```

`render_with_remotion`：

- `cwd = remotion_project_dir()`
- 使用 **显式** `[Path(AINEWS_NODE_HOME) / "npx.cmd", "remotion", "render", ...]`，不依赖残缺 PATH。

环境变量统一 **`AINEWS_NODE_HOME`**（禁止 `AINES_*`）。仅在 `backend::spawn_backend` 注入 `PATH` 与 `REMOTION_PROJECT_DIR`；单独 CLI 起 `web_server.py` 不享受便携 Node（文档说明）。

---

## 8. 应用升级与 lock 绑定（必改）

`remotion_v1.json` 必含：

```json
{
  "install_id": "remotion_v1",
  "app_version": "1.0.15",
  "remotion_lock_sha256": "<sha256 of app_dir/remotion/package-lock.json>",
  "node_version": "20.x.x",
  "completed_at": "ISO8601"
}
```

出片或 `GET /api/runtime/video-renderer` 时：若当前 `get_app_version()` 或 bundle 内 lock 的 sha 与 marker 不一致 → `remotion.ready=false`，`reason=upgrade_required`，设置页提示 **「请重新安装 Remotion 运行时」**。

桌面包 **必须** 包含 `remotion/package.json` + `package-lock.json`（`build-release-fast` 已拷贝 `remotion/` 目录，需在构建检查中 assert）。

---

## 9. 可观测性（必改）

`run_media_pipeline` 的 `steps.render_video`（及失败时的 error 对象）增加：

```json
{ "renderer": "remotion" | "python", "fallback_from": "remotion" | null, "reason": "..." }
```

可选 P1：`video_draft_json.renderer` 冗余字段供资讯库展示「上次成片引擎」。

---

## 10. 技术架构

### 10.1 目录布局

```text
{AINEWS_DATA_DIR}/
  runtime/
    remotion_v1.json
    node/                     # 便携 Node（P1）
    remotion-project/         # package.json + lock + node_modules（P1）
    remotion-browser/
    logs/remotion_setup.log
  playwright-browsers/
```

```text
{app_dir}/remotion/           # 只读源码 + lock，无 node_modules
```

### 10.2 P1 安装步骤（Tauri `remotion_setup_run`）

1. 按 `desktop/remotion-runtime-manifest.json` 下载 Node LTS zip（HTTPS + SHA256）
2. 从 `app_dir/remotion` 同步到 `data/runtime/remotion-project/`（保留 lock）
3. `npm ci --omit=dev`（支持 `desktop_runtime.local.yaml` 的 `npm_registry`；**P1 最低** bundle 内 `npm-cache` 或镜像配置）
4. `npx remotion browser ensure`（浏览器目录 `remotion-browser/`)
5. 探测 + 写 marker

进度事件：`ainews:remotion-setup-progress`（对齐 `ainews:setup-progress`）。

### 10.3 P1 前置调研（开工前完成，原 P2 提前）

| # | 项 | 产出 |
|---|-----|------|
| R1 | Remotion 浏览器 vs Playwright Chromium 能否共用 | 决策 + UI 体积文案（约 ___ GB） |
| R2 | 国内 npm 策略 | 默认 registry / 离线 cache 方案 |
| R3 | packaged 下 `remotion/` 路径 | 集成测试 assert lock 在 bundle |
| R4 | `npx` 显式路径 | spike 在 Windows 子进程 |

### 10.4 安全（P1）

- Node zip URL、版本、SHA256 固定在仓库 `desktop/remotion-runtime-manifest.json`
- 禁止运行时任意 URL
- 与桌面更新通道版本策略一致

---

## 11. 与 Playwright 运行时

| | Playwright | Remotion |
|--|------------|----------|
| 入口 | 登录后 `runtime_setup_run` | **设置页** + 可选首次出片 toast（P2） |
| 浏览器 | `playwright-browsers` | `remotion-browser`（默认独立） |

---

## 12. 系统配置页 —「成片引擎」Tab

（结构同 v1.0 §6.1–6.5，文案修正如下。）

**自动模式说明（必改文案）：**

> 自动：Remotion 就绪时使用 React 成片引擎；否则使用内置 Python 引擎。两种引擎在个别模板上可能有细微差异，并非像素级完全一致。

**区块 C** 仅 Tauri；Web 显示仓库 `npm install` 说明。

**区块 D** 展示 `VIDEO_RENDERER` 只读；优先级见 §5。

**成片模板 Tab（P0）** 顶栏：`当前成片引擎：{active}` + 链接本 Tab。

### 12.1 建议（非 blocking）：运行环境聚合

P2 可选 `GET /api/runtime/summary`：Playwright / Remotion / ML extras 一张卡片列表，设置页「运行环境」父 Tab 下分子卡片，避免 Tab 过多。P0 仍独立「成片引擎」Tab。

---

## 13. API

### `GET /api/runtime/video-renderer`

```json
{
  "preferred": "auto",
  "allow_python_fallback": true,
  "consistent": true,
  "repair_hint": null,
  "remotion": {
    "ready": false,
    "reason": "node_modules_missing",
    "project_dir": "...",
    "node_version": null,
    "lock_sha256": null,
    "upgrade_required": false
  },
  "python": { "ready": true, "layouts": ["chronicle_frame", "classic_overlay"] },
  "active": "python",
  "env_override": null,
  "last_render_renderer": null
}
```

### `PUT /api/runtime/video-renderer`

```json
{ "preferred": "auto", "allow_python_fallback": true }
```

### Tauri（P1）

`remotion_setup_status` | `remotion_setup_run` | `remotion_setup_cancel`（可选）

---

## 14. `desktop_runtime.local.yaml`

```yaml
video_renderer:
  preferred: auto
  allow_python_fallback: true
npm:
  registry: null   # P1，空则用 npm 默认
```

---

## 15. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 体积大 | UI 预估；R1 调研共用浏览器 |
| npm 失败 | P1 镜像 + cache；非仅 P2 tarball |
| 升级后坏片 | lock_sha + upgrade_required |
| 双 Chromium | R1 + 文案 |
| UI 与行为不一致 | §6 矩阵 + P0 fallback 实现 |

---

## 16. 测试策略（必改章节）

| 层 | 内容 |
|----|------|
| 单测 | `resolve_video_renderer` 矩阵（env / yaml / packaged 默认） |
| 单测 | §6 矩阵：`remotion_not_ready` vs fallback |
| 集成 | mock `remotion_available` / `render_with_remotion` 失败 → Python + `steps.renderer` |
| 桌面 e2e | 不跑真 Remotion；marker fixture 模拟 ready |
| 构建 | assert `bundle-resources/app/remotion/package-lock.json` 存在 |

---

## 17. 验收标准

- **P0**：设置页状态/保存；`allow_python_fallback=false` + `preferred=remotion` 且无 Node → 出片明确失败；`steps.render_video.renderer` 有值。
- **P1**：干净桌面包安装后 `remotion.ready=true` 且探测通过；日志 `renderer=remotion`；升级 app 后 `upgrade_required`。
- **任意**：fallback 开时 Remotion 失败仍出片；playbook 归因不受影响。

---

## 附录 A：为何首包不带 Remotion

1. `node_modules` 不进 Git、体积大。  
2. 需要 Node + npx。  
3. Remotion 可能再拉专用浏览器。  
4. 首包约 1.5GB 级；成片质量按需安装。

---

## 附录 B：架构师 Review 记录（v1.0 → v1.1）

- 合入：配置/marker SSOT、决策矩阵、升级绑定、探测、可观测性、优先级、文案、测试、P1 调研提前、安全 manifest、`AINEWS_NODE_HOME`。
- 决议：**有条件通过**；按 `docs/superpowers/plans/2026-09-24-remotion-desktop-optional.md` 实施。
