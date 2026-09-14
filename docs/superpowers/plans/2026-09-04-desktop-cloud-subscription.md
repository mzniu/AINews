# AINews 桌面客户端 + 轻量云订阅 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AINews 交付为 Tauri 2 桌面应用（完整窗口），配套轻量云端（认证 / 订阅 / 配置同步），本地保留全部业务与 Playwright 发布能力。

**Architecture:** **Local-first Data Plane**（现有 FastAPI + SQLite + Playwright）+ **Cloud Control Plane**（独立 `cloud/` FastAPI + PostgreSQL）。Tauri 管理 Python 子进程、云登录、配置 reconcile；`AINEWS_DATA_DIR` 分离用户数据与安装目录。

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2.x · SQLite WAL · Playwright · Tauri 2 · Rust · WebView2 · PostgreSQL 15+ · JWT (`python-jose`) · bcrypt · PyYAML

**Spec:** [docs/superpowers/specs/2026-09-04-desktop-cloud-subscription-design.md](../specs/2026-09-04-desktop-cloud-subscription-design.md) v1.0

## Global Constraints

- 桌面：**Tauri 2 + WebView2**；加载 `http://127.0.0.1:{PORT}`；**不重写** `static/` 为 SPA
- 云同步：**仅** `config/*.local.yaml` 白名单（9 个 key）；**禁止**同步 `data/`、`.env`、发布 session / browser profile
- `publishing_platforms.local` 同步须剥离：`session_path`、`browser_profile_path` 及任何绝对路径
- 配置冲突：**last-write-wins（`updated_at`）**；hash 冲突时 UI 手动选择
- 订阅：Workspace 为计费单元；V1 仅 `personal` workspace；`organization` 仅 DB schema 预留
- 离线宽限：**Pro/Team 7 天**；**Free 3 天**；过期 **软限制**（禁新建 AI 总结 / 发布 / 绑号；可查看导出）
- 开发模式：`AINES_DEV_MODE=1` 跳过云登录与 `EntitlementGuard`
- 发布：**100% 本地 Playwright**；不改动 `publish-worker` 架构
- V1 **不做**：内容库 / 视频上云、应用内支付、organization UI、E2E 配置加密、macOS
- 前置门禁：**P0 路径抽象 + P1 Tauri MVP** 通过后再冻结 `cloud/` API schema

---

## File Map

| 文件 | 职责 |
|------|------|
| `src/utils/paths.py` | `get_data_dir()` / `get_resource_dir()` / `get_config_dir()` / `is_packaged()` |
| `src/utils/config.py` | 改用 `paths`；`DATABASE_URL` 基于 `get_data_dir()` |
| `src/db/engine.py` | `_database_url()` 使用 `get_data_dir()` |
| `api/routes/health_routes.py` | `GET /api/health` |
| `web_server.py` | 静态路径、`health` router、`AINEWS_*` env |
| `scripts/portable_launcher.ps1` | P0 验证：AppData 启动 |
| `desktop/src-tauri/` | Tauri 壳：单实例、Python 进程、托盘 |
| `desktop/scripts/build-python.ps1` | 嵌入式 venv 构建 |
| `static/auth.html` | 登录 / 注册页（调云 API） |
| `cloud/` | 轻量云 Control Plane |
| `cloud/app/main.py` | 云 FastAPI 入口 |
| `cloud/app/models/` | SQLAlchemy ORM |
| `cloud/app/routers/auth.py` | 注册 / 登录 / JWT |
| `cloud/app/routers/entitlements.py` | 订阅 / 配额 |
| `cloud/app/routers/config_sync.py` | manifest + blob CRUD |
| `services/entitlements/guard.py` | 本地门控 |
| `services/entitlements/cache.py` | 读 `entitlements.json` |
| `services/cloud_sync/manifest.py` | 本地 manifest 读写 |
| `services/cloud_sync/sanitize.py` | 配置字段过滤 |
| `services/cloud_sync/reconcile.py` | 双向同步逻辑 |
| `api/routes/settings_routes.py` | 同步状态 / 冲突解决 API |
| `static/settings.html` + JS | 同步 UI、过期横幅 |
| `tests/test_paths.py` | 路径抽象单测 |
| `tests/test_cloud_sync_sanitize.py` | sanitizer 单测 |
| `tests/test_entitlements_guard.py` | 门控单测 |
| `cloud/tests/` | 云 API 测试 |

---

## Phase P0 — 路径抽象（门禁，必须先完成）

### Task 1: `paths.py` 模块

**Files:**
- Create: `src/utils/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces:
  - `get_data_dir() -> Path`
  - `get_resource_dir() -> Path`
  - `get_config_dir() -> Path`
  - `is_packaged() -> bool`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_paths.py
from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_get_data_dir_defaults_to_repo_data(monkeypatch, tmp_path):
    monkeypatch.delenv("AINEWS_DATA_DIR", raising=False)
    repo = tmp_path / "repo"
    (repo / "src" / "utils").mkdir(parents=True)
    # paths.py 用 __file__ 定位；测试中 monkeypatch get_resource_dir 的父级
    from src.utils import paths

    monkeypatch.setattr(paths, "_detect_resource_dir", lambda: repo)
    assert paths.get_data_dir() == repo / "data"


def test_get_data_dir_respects_env(monkeypatch, tmp_path):
    custom = tmp_path / "appdata"
    custom.mkdir()
    monkeypatch.setenv("AINEWS_DATA_DIR", str(custom))
    from src.utils import paths

    assert paths.get_data_dir() == custom


def test_get_config_dir_under_data_dir(monkeypatch, tmp_path):
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data))
    from src.utils import paths

    assert paths.get_config_dir() == data / "config"
```

- [ ] **Step 2: 运行确认失败**

```bash
pytest tests/test_paths.py -v
```

Expected: FAIL（`paths` 模块不存在）

- [ ] **Step 3: 实现 `paths.py`**

```python
# src/utils/paths.py
"""Runtime path resolution for dev, portable, and packaged desktop builds."""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path


def _detect_resource_dir() -> Path:
    env = os.getenv("AINEWS_RESOURCE_DIR", "").strip()
    if env:
        return Path(env).resolve()
    # dev: repo root (src/utils/paths.py -> parents[2])
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_resource_dir() -> Path:
    return _detect_resource_dir()


def is_packaged() -> bool:
    return bool(os.getenv("AINEWS_RESOURCE_DIR", "").strip()) or getattr(sys, "frozen", False)


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    env = os.getenv("AINEWS_DATA_DIR", "").strip()
    if env:
        return Path(env).resolve()
    return get_resource_dir() / "data"


def get_config_dir() -> Path:
    return get_data_dir() / "config"


def ensure_runtime_dirs() -> None:
    for d in (
        get_data_dir(),
        get_config_dir(),
        get_data_dir() / "logs",
        get_data_dir() / "cache",
        get_data_dir() / "videos",
        get_data_dir() / "publish" / "sessions",
        get_data_dir() / "publish" / "profiles",
        get_data_dir() / "publish" / "qr",
    ):
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: 运行测试通过**

```bash
pytest tests/test_paths.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/paths.py tests/test_paths.py
git commit -m "feat(paths): add runtime data/resource dir resolution"
```

---

### Task 2: `Config` 与 `engine` 接入 paths

**Files:**
- Modify: `src/utils/config.py`
- Modify: `src/db/engine.py`
- Test: `tests/test_paths.py`（追加 1 个集成测试）

**Interfaces:**
- Consumes: `get_data_dir()`, `get_resource_dir()`, `get_config_dir()`, `ensure_runtime_dirs()`
- Produces: `Config.DATA_DIR` 指向 `get_data_dir()`；`Config.ROOT_DIR` 保留为 `get_resource_dir()`（只读资源）

- [ ] **Step 1: 修改 `config.py`**

```python
# src/utils/config.py — 关键改动
from src.utils.paths import ensure_runtime_dirs, get_config_dir, get_data_dir, get_resource_dir

class Config:
    ROOT_DIR = get_resource_dir()      # 只读：static、默认 config 基线
    DATA_DIR = get_data_dir()
    CONFIG_DIR = get_config_dir()
    # ... VIDEO_DIR = DATA_DIR / "videos" 等全部改为基于 DATA_DIR
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'ainews.db').as_posix()}",
    )

    @classmethod
    def load_sources(cls) -> Dict[str, Any]:
        config_file = cls.ROOT_DIR / "config" / "sources.yaml"
        # 不变

ensure_runtime_dirs()  # 替换 Config.ensure_dirs()
```

- [ ] **Step 2: 修改 `engine.py` `_database_url`**

```python
# src/db/engine.py
from src.utils.paths import get_data_dir

def _database_url() -> str:
    env_url = os.getenv("INGESTION_DATABASE_URL")
    if env_url:
        return env_url
    db_path = get_data_dir() / "ainews.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"
```

- [ ] **Step 3: 运行全量测试确认无回归**

```bash
pytest tests/test_paths.py tests/test_publishing_qr_login_upsert.py -v
```

Expected: PASS（已有测试用 `monkeypatch Config.ROOT_DIR` 的仍应通过）

- [ ] **Step 4: Commit**

```bash
git add src/utils/config.py src/db/engine.py
git commit -m "refactor(config): route data paths through paths module"
```

---

### Task 3: `web_server.py` 静态挂载 + health 端点

**Files:**
- Create: `api/routes/health_routes.py`
- Modify: `web_server.py`
- Test: `tests/test_health_routes.py`

**Interfaces:**
- Produces: `GET /api/health` → `{"status":"ok","version":str,"data_dir":str,"packaged":bool}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_health_routes.py
from fastapi.testclient import TestClient
from web_server import app

def test_health_ok():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "data_dir" in body
```

- [ ] **Step 2: 实现 health router**

```python
# api/routes/health_routes.py
from fastapi import APIRouter
from src.utils.paths import get_data_dir, is_packaged

router = APIRouter(prefix="/api", tags=["health"])

APP_VERSION = "2.0.0"

@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "data_dir": str(get_data_dir()),
        "packaged": is_packaged(),
    }
```

- [ ] **Step 3: 注册 router；静态目录改用 `Config.ROOT_DIR`**

```python
# web_server.py 改动要点
from api.routes.health_routes import router as health_router
from src.utils.config import Config

app.mount("/static", StaticFiles(directory=str(Config.ROOT_DIR / "static")), name="static")
app.mount("/data", StaticFiles(directory=str(Config.DATA_DIR)), name="data")
app.include_router(health_router)  # 放在 main_router 之前
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_health_routes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add api/routes/health_routes.py web_server.py tests/test_health_routes.py
git commit -m "feat(api): add /api/health and fix static mount paths"
```

---

### Task 4: 便携启动器验证（P0 门禁）

**Files:**
- Create: `scripts/portable_launcher.ps1`
- Modify: `services/ingestion/settings.py` 等（将 `*.local.yaml` 路径改为 `Config.CONFIG_DIR`）

**Interfaces:**
- Consumes: `AINEWS_DATA_DIR`
- Produces: 验证数据写入 `%APPDATA%\AINews` 而非 repo `data/`

- [ ] **Step 1: 批量替换 local config 路径**

将以下文件中的 `Config.ROOT_DIR / "config"` 改为 `Config.CONFIG_DIR`：

- `services/ingestion/settings.py`
- `services/content_prompts.py`
- `services/ingestion/scoring_settings.py`
- `services/ingestion/image_scoring_settings.py`
- `services/ingestion/hot_radar_settings.py`
- `services/ingestion/render_templates.py`（若存在）
- `services/publishing/registry.py`（local override 路径）
- `services/publishing/comment_reply/settings.py`
- `services/publishing/first_comment_settings.py`
- `utils/forbidden_words.py`（`LOCAL_CONFIG_PATH`）

- [ ] **Step 2: 创建启动脚本**

```powershell
# scripts/portable_launcher.ps1
$DataDir = Join-Path $env:APPDATA "AINews"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$env:AINEWS_DATA_DIR = $DataDir
$env:PORT = "8088"
Write-Host "AINEWS_DATA_DIR=$DataDir"
python web_server.py
```

- [ ] **Step 3: 手动门禁**

```powershell
.\scripts\portable_launcher.ps1
# 另一终端：
curl http://localhost:8088/api/health
```

Expected: `data_dir` 为 `C:\Users\<user>\AppData\Roaming\AINews`；`data\ainews.db` 出现在 AppData 而非 repo。

- [ ] **Step 4: Commit**

```bash
git add scripts/portable_launcher.ps1 services/ utils/forbidden_words.py
git commit -m "feat(desktop-p0): portable launcher and config dir under AINEWS_DATA_DIR"
```

**P0 Gate:** `curl /api/health` 的 `data_dir` 在 AppData；现有 `pytest` 无新增失败。

---

## Phase P1 — Tauri 桌面 MVP

### Task 5: 初始化 Tauri 项目

**Files:**
- Create: `desktop/`（`cargo tauri init` 产出）
- Create: `desktop/README.md`

**Interfaces:**
- Produces: `desktop/src-tauri/tauri.conf.json` 中 `productName: "AINews"`，`identifier: "com.ainews.desktop"`

- [ ] **Step 1: 安装前置**

```powershell
# 需 Rust stable + Node 18+ + Visual Studio Build Tools
cargo install tauri-cli --version "^2.0.0"
```

- [ ] **Step 2: 在 `desktop/` 初始化**

```powershell
cd desktop
cargo tauri init
# window title: AINews
# dev path: http://localhost:8088
# dist dir: ../static  (占位，生产用 WebView 导航)
```

- [ ] **Step 3: 配置 `tauri.conf.json` 关键项**

```json
{
  "productName": "AINews",
  "identifier": "com.ainews.desktop",
  "app": {
    "windows": [{ "title": "AINews", "width": 1280, "height": 800 }]
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add desktop/
git commit -m "chore(desktop): scaffold Tauri 2 project"
```

---

### Task 6: Python 子进程管理（`backend.rs`）

**Files:**
- Create: `desktop/src-tauri/src/backend.rs`
- Modify: `desktop/src-tauri/src/main.rs`
- Modify: `desktop/src-tauri/Cargo.toml`（`windows` crate for Job Object）

**Interfaces:**
- Produces:
  - `struct BackendProcess { child: Child, job: Option<windows::Win32::...> }`
  - `fn spawn_backend(port: u16, data_dir: &Path) -> Result<BackendProcess>`
  - `fn wait_for_health(port: u16, timeout: Duration) -> Result<()>`
  - `fn shutdown_backend(proc: BackendProcess)`

- [ ] **Step 1: 实现 `backend.rs`（开发模式：调用 repo venv python）**

```rust
// desktop/src-tauri/src/backend.rs
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

pub struct BackendProcess {
    pub child: Child,
}

pub fn resolve_python_exe(resource_dir: &PathBuf) -> PathBuf {
    let packaged = resource_dir.join("python/python.exe");
    if packaged.exists() {
        return packaged;
    }
    // dev fallback
    PathBuf::from("python")
}

pub fn spawn_backend(
    python: &PathBuf,
    app_dir: &PathBuf,
    data_dir: &PathBuf,
    port: u16,
) -> std::io::Result<BackendProcess> {
    let child = Command::new(python)
        .current_dir(app_dir)
        .env("AINEWS_DATA_DIR", data_dir)
        .env("AINEWS_RESOURCE_DIR", app_dir)
        .env("PORT", port.to_string())
        .env("AINES_DEV_MODE", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    Ok(BackendProcess { child })
}

pub fn wait_for_health(port: u16, timeout: Duration) -> Result<(), String> {
    let client = reqwest::blocking::Client::new();
    let url = format!("http://127.0.0.1:{port}/api/health");
    let start = Instant::now();
    while start.elapsed() < timeout {
        if let Ok(resp) = client.get(&url).send() {
            if resp.status().is_success() {
                return Ok(());
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    Err("backend health check timeout".into())
}

impl BackendProcess {
    pub fn shutdown(mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
```

- [ ] **Step 2: `main.rs` 启动流程**

```rust
// desktop/src-tauri/src/main.rs 核心逻辑
mod backend;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let resource_dir = /* repo root in dev */;
            let data_dir = dirs::data_dir().unwrap().join("AINews");
            let port = 8088u16;
            let python = backend::resolve_python_exe(&resource_dir);
            let proc = backend::spawn_backend(&python, &resource_dir, &data_dir, port)?;
            backend::wait_for_health(port, Duration::from_secs(60))?;
            app.manage(proc);
            let win = app.get_webview_window("main").unwrap();
            win.navigate_url(format!("http://127.0.0.1:{port}").parse().unwrap())?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 3: 添加依赖**

```toml
# desktop/src-tauri/Cargo.toml
[dependencies]
reqwest = { version = "0.12", features = ["blocking"] }
dirs = "5"
```

- [ ] **Step 4: 开发模式验证**

```powershell
# 终端 1：不手动起 web_server
cd desktop
cargo tauri dev
```

Expected: 窗口打开并显示 AINews 首页。

- [ ] **Step 5: Commit**

```bash
git add desktop/src-tauri/
git commit -m "feat(desktop): spawn Python backend and navigate WebView"
```

---

### Task 7: 单实例 + 托盘 + 退出清理

**Files:**
- Create: `desktop/src-tauri/src/tray.rs`
- Modify: `desktop/src-tauri/src/main.rs`

**Interfaces:**
- Produces: Windows Mutex `AINews.SingleInstance`；托盘菜单：显示/隐藏、打开数据目录、退出

- [ ] **Step 1: 单实例检查（Windows）**

```rust
#[cfg(windows)]
fn ensure_single_instance() -> Result<(), String> {
    use windows_sys::Win32::System::Threading::CreateMutexW;
    // Mutex 名 L"AINews.SingleInstance"
    // ERROR_ALREADY_EXISTS => exit
    Ok(())
}
```

- [ ] **Step 2: 系统托盘**

使用 `tauri::tray::TrayIconBuilder`：菜单项调用 `open_data_dir`、`show_window`、`quit`（quit 时 `BackendProcess::shutdown`）。

- [ ] **Step 3: `on_window_event` CloseRequested → shutdown backend**

- [ ] **Step 4: 手动验证**

启动两次 exe → 第二次应提示已运行；托盘退出后 `python` 进程消失（`tasklist | findstr python`）。

- [ ] **Step 5: Commit**

```bash
git add desktop/src-tauri/src/tray.rs desktop/src-tauri/src/main.rs
git commit -m "feat(desktop): single instance, tray, and backend cleanup"
```

**P1 Gate:** 干净 Win10 上 `cargo tauri dev` 可打开完整 UI；退出无僵尸 Python 进程。

---

## Phase P2 — 安装包与依赖捆绑

### Task 8: `build-python.ps1` 嵌入式 venv

**Files:**
- Create: `desktop/scripts/build-python.ps1`
- Create: `desktop/scripts/bundle-browsers.ps1`

- [ ] **Step 1: `build-python.ps1` 流程**

```powershell
# 1. 下载 python-3.11.x-embed-amd64.zip 到 desktop/build/cache/
# 2. pip install -r requirements.txt --target desktop/build/staging/python/Lib
# 3. 复制 repo 源码到 desktop/build/staging/app/（排除 data、.venv、tests）
# 4. 输出到 desktop/src-tauri/resources/
```

- [ ] **Step 2: `bundle-browsers.ps1`**

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "desktop/build/staging/playwright-browsers"
python -m playwright install chromium
```

- [ ] **Step 3: 捆绑 ffmpeg**

下载 [BtbN FFmpeg builds](https://github.com/BtbN/FFmpeg-Builds/releases) `ffmpeg-master-latest-win64-gpl.zip`，解压 `bin/ffmpeg.exe` 到 `resources/ffmpeg/`。

- [ ] **Step 4: `tauri.conf.json` bundle resources**

- [ ] **Step 5: 打包验证**

```powershell
cd desktop
.\scripts\build-python.ps1
cargo tauri build
```

Expected: `target/release/bundle/` 产出安装包；安装后视频抓取流程可用。

- [ ] **Step 6: Commit**

```bash
git add desktop/scripts/ desktop/src-tauri/tauri.conf.json
git commit -m "feat(desktop): bundle python, playwright, and ffmpeg"
```

---

## Phase P3 — 轻量云 Control Plane

### Task 9: Cloud 项目脚手架

**Files:**
- Create: `cloud/pyproject.toml` 或 `cloud/requirements.txt`
- Create: `cloud/app/main.py`
- Create: `cloud/app/database.py`
- Create: `cloud/docker-compose.yml`（PostgreSQL 本地开发）
- Create: `cloud/.env.example`

**Interfaces:**
- Produces: `uvicorn app.main:app` 运行于 `:8090`

- [ ] **Step 1: `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: ainews
      POSTGRES_PASSWORD: ainews
      POSTGRES_DB: ainews_cloud
    ports:
      - "5432:5432"
```

- [ ] **Step 2: `cloud/requirements.txt`**

```
fastapi>=0.104
uvicorn[standard]>=0.24
sqlalchemy>=2.0
psycopg2-binary>=2.9
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
pydantic[email]>=2.0
alembic>=1.13
```

- [ ] **Step 3: 最小 `main.py` + `GET /health`**

- [ ] **Step 4: 启动验证**

```bash
cd cloud && docker compose up -d && pip install -r requirements.txt
uvicorn app.main:app --port 8090
curl http://localhost:8090/health
```

- [ ] **Step 5: Commit**

```bash
git add cloud/
git commit -m "feat(cloud): scaffold control plane service"
```

---

### Task 10: 数据库模型与 Alembic 迁移

**Files:**
- Create: `cloud/app/models/user.py`
- Create: `cloud/app/models/workspace.py`
- Create: `cloud/app/models/subscription.py`
- Create: `cloud/app/models/config_blob.py`
- Create: `cloud/alembic/versions/001_initial.py`

**Interfaces:**
- Produces: 表 `users`, `workspaces`, `workspace_members`, `subscriptions`, `config_blobs`, `devices`（与 spec §5.2 一致）

- [ ] **Step 1: 按 spec §5.2 编写 ORM**

- [ ] **Step 2: 生成并运行迁移**

```bash
cd cloud && alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add cloud/app/models cloud/alembic
git commit -m "feat(cloud): add multi-tenant schema migration"
```

---

### Task 11: 认证 API

**Files:**
- Create: `cloud/app/routers/auth.py`
- Create: `cloud/app/services/auth_service.py`
- Create: `cloud/app/deps.py`（`get_current_user`）
- Test: `cloud/tests/test_auth.py`

**Interfaces:**
- Produces:
  - `POST /auth/register` → 创建 user + personal workspace + free subscription
  - `POST /auth/login` → `{ access_token, refresh_token, expires_in }`
  - `POST /auth/refresh`
  - `GET /me` → `{ user, workspace }`

- [ ] **Step 1: 写失败测试（注册 + 登录）**

```python
def test_register_and_login(client):
    r = client.post("/auth/register", json={"email": "a@b.com", "password": "secret123"})
    assert r.status_code == 201
    r2 = client.post("/auth/login", json={"email": "a@b.com", "password": "secret123"})
    assert "access_token" in r2.json()
```

- [ ] **Step 2: 实现 bcrypt 哈希 + JWT（HS256，secret 来自 env）**

- [ ] **Step 3: 注册时自动创建**

```python
workspace = Workspace(type="personal", name=email.split("@")[0], owner_user_id=user.id)
subscription = Subscription(workspace_id=workspace.id, plan_id="free", status="active")
```

- [ ] **Step 4: 测试通过 + Commit**

```bash
git add cloud/app/routers/auth.py cloud/tests/test_auth.py
git commit -m "feat(cloud): auth register/login with personal workspace"
```

---

### Task 12: Entitlements API

**Files:**
- Create: `cloud/app/routers/entitlements.py`
- Create: `cloud/app/services/plans.py`
- Test: `cloud/tests/test_entitlements.py`

**Interfaces:**
- Produces: `GET /entitlements` 响应格式见 spec §7.2

- [ ] **Step 1: `plans.py` 硬编码 V1 套餐**

```python
PLANS = {
    "free": {"ai_summaries_per_month": 20, "publish_accounts": 0, "config_sync_enabled": False, "offline_grace_days": 3},
    "pro":  {"ai_summaries_per_month": 500, "publish_accounts": 3, "config_sync_enabled": True, "offline_grace_days": 7},
    "team": {"ai_summaries_per_month": 2000, "publish_accounts": 10, "config_sync_enabled": True, "offline_grace_days": 7},
}
```

- [ ] **Step 2: 实现 `GET /entitlements`（含 `offline_grace_until` 计算）**

- [ ] **Step 3: 管理脚本手动升级套餐（V1 无支付）**

```python
# cloud/scripts/set_plan.py --email user@x.com --plan pro
```

- [ ] **Step 4: Commit**

```bash
git add cloud/app/routers/entitlements.py cloud/scripts/set_plan.py
git commit -m "feat(cloud): entitlements endpoint and manual plan setter"
```

---

### Task 13: `static/auth.html` + Tauri 登录流

**Files:**
- Create: `static/auth.html`
- Create: `static/js/auth.js`
- Modify: `desktop/src-tauri/src/main.rs`（无 token 时加载 auth 页）
- Create: `desktop/src-tauri/src/auth.rs`

**Interfaces:**
- Consumes: 云 API `POST /auth/login`、`POST /auth/register`
- Produces: refresh_token 存 Windows Credential Manager（`keyring` crate）

- [ ] **Step 1: `auth.html` 表单 + `auth.js` 调 `AINEWS_CLOUD_API` env**

- [ ] **Step 2: Tauri 启动检查 token；无则 `navigate` 到 `auth.html?cloud_api=...`**

- [ ] **Step 3: 登录成功后 `GET /entitlements` → 写 `%APPDATA%/AINews/cache/entitlements.json`**

- [ ] **Step 4: 再启动 Python backend**

- [ ] **Step 5: 手动 E2E：注册 → 登录 → 进入主页**

- [ ] **Step 6: Commit**

```bash
git add static/auth.html static/js/auth.js desktop/src-tauri/src/auth.rs
git commit -m "feat(desktop): cloud login flow with token storage"
```

**P3 Gate:** 登录后 `entitlements.json` 存在且 `plan_id` 正确。

---

## Phase P4 — 配置云同步

### Task 14: Config Sync 云 API

**Files:**
- Create: `cloud/app/routers/config_sync.py`
- Test: `cloud/tests/test_config_sync.py`

**Interfaces:**
- Produces: `GET /sync/config/manifest`、`GET /sync/config/{key}`、`PUT /sync/config/{key}`
- 校验：`config_sync_enabled` entitlement；非法 `config_key` → 400

- [ ] **Step 1: 白名单常量**

```python
SYNC_CONFIG_KEYS = frozenset({
    "content_prompts.local",
    "models.local",
    "ingestion.local",
    "article_scoring.local",
    "image_scoring.local",
    "render_templates.local",
    "hot_radar.local",
    "forbidden_words.local",
    "publishing_platforms.local",
})
```

- [ ] **Step 2: PUT 时计算 `content_hash = sha256(content_yaml)`**

- [ ] **Step 3: Free 套餐 PUT/GET → 403**

- [ ] **Step 4: Commit**

```bash
git add cloud/app/routers/config_sync.py cloud/tests/test_config_sync.py
git commit -m "feat(cloud): config sync manifest and blob API"
```

---

### Task 15: 本地 sanitizer + reconcile

**Files:**
- Create: `services/cloud_sync/sanitize.py`
- Create: `services/cloud_sync/manifest.py`
- Create: `services/cloud_sync/reconcile.py`
- Create: `services/cloud_sync/keys.py`
- Test: `tests/test_cloud_sync_sanitize.py`

**Interfaces:**
- Produces:
  - `CONFIG_KEY_TO_FILENAME: dict[str, str]`
  - `sanitize_for_upload(config_key: str, yaml_text: str) -> str`
  - `load_local_manifest() -> dict`
  - `reconcile_with_cloud(cloud_api_base: str, token: str) -> ReconcileResult`

- [ ] **Step 1: sanitizer 测试（blocking 门禁）**

```python
def test_strips_session_path_from_publishing_platforms():
    raw = """
    defaults:
      comment_reply: {mode: inline}
    accounts:
      - session_path: data/publish/sessions/abc.enc
        browser_profile_path: data/publish/profiles/abc
    """
    out = sanitize_for_upload("publishing_platforms.local", raw)
    assert "session_path" not in out
    assert "browser_profile_path" not in out
    assert "inline" in out
```

- [ ] **Step 2: 实现 `sanitize.py`（YAML parse → 递归删除敏感键）**

- [ ] **Step 3: `reconcile.py` 按 spec §6.3 逻辑**

- [ ] **Step 4: Commit**

```bash
git add services/cloud_sync/ tests/test_cloud_sync_sanitize.py
git commit -m "feat(sync): config sanitizer and reconcile logic"
```

---

### Task 16: Tauri sync 模块 + 设置页 UI

**Files:**
- Create: `desktop/src-tauri/src/sync.rs`
- Create: `api/routes/settings_routes.py`
- Modify: `static/settings.html` + `static/js/settings_content_prompts.js`（或新建 `settings_sync.js`）

**Interfaces:**
- Consumes: `reconcile_with_cloud()`
- Produces: 设置页展示「上次同步时间 / 冲突列表」；按钮「从云端恢复」「推送到云端」

- [ ] **Step 1: Tauri 启动时调用 `sync::reconcile()`（在 backend 启动前）**

- [ ] **Step 2: `GET /api/settings/sync-status` 读本地 manifest**

- [ ] **Step 3: 设置页增加同步卡片 UI**

- [ ] **Step 4: 双机手动测试：A 改 prompt → 同步 → B 拉取一致**

- [ ] **Step 5: Commit**

```bash
git add desktop/src-tauri/src/sync.rs api/routes/settings_routes.py static/
git commit -m "feat(sync): desktop reconcile on startup and settings UI"
```

**P4 Gate:** 两台设备配置一致；sanitizer 测试确认 session 字段不上云。

---

## Phase P5 — Entitlement 门控

### Task 17: 本地 entitlements 缓存与 guard

**Files:**
- Create: `services/entitlements/cache.py`
- Create: `services/entitlements/guard.py`
- Create: `services/entitlements/errors.py`
- Test: `tests/test_entitlements_guard.py`

**Interfaces:**
- Produces:
  - `load_entitlements() -> dict | None`
  - `check_entitlement(feature: str) -> None`  # raises EntitlementError
  - `is_expired_soft() -> bool`

- [ ] **Step 1: 失败测试**

```python
def test_blocks_ai_summary_when_expired(tmp_path, monkeypatch):
    cache = tmp_path / "entitlements.json"
    cache.write_text('{"status":"past_due","offline_grace_until":"2020-01-01T00:00:00Z","limits":{}}', encoding="utf-8")
    monkeypatch.setenv("AINES_DEV_MODE", "0")
    monkeypatch.setattr("services.entitlements.cache.ENTITLEMENTS_PATH", cache)
    with pytest.raises(EntitlementError):
        check_entitlement("ai_summary")
```

- [ ] **Step 2: 实现 guard（`AINES_DEV_MODE=1` 直接 return）**

- [ ] **Step 3: Commit**

```bash
git add services/entitlements/ tests/test_entitlements_guard.py
git commit -m "feat(entitlements): local cache and entitlement guard"
```

---

### Task 18: 路由门控接入

**Files:**
- Modify: `api/routes/crawler_routes.py`（`generate-summary`）
- Modify: `api/routes/publishing_routes.py`（`qr-start`、新建 publish job）
- Modify: `services/ingestion/story_cluster_llm.py`（自动总结，可选）

- [ ] **Step 1: 在 `POST /api/generate-summary` 入口调用 `check_entitlement("ai_summary")`**

- [ ] **Step 2: 在 `POST /api/publishing/accounts/qr-start` 调用 `check_entitlement("publish_account")`**

- [ ] **Step 3: 捕获 `EntitlementError` → HTTP 402 + `{"code":"entitlement_required","feature":"..."}`**

- [ ] **Step 4: 测试 + Commit**

```bash
git add api/routes/crawler_routes.py api/routes/publishing_routes.py
git commit -m "feat(entitlements): gate AI summary and publish account binding"
```

---

### Task 19: 过期软限制 UI

**Files:**
- Modify: `static/js/shared/app_nav.js` 或 `app_shell` 相关
- Modify: `static/settings.html`

- [ ] **Step 1: `GET /api/entitlements/status`（读本地缓存，不打云）**

- [ ] **Step 2: 全局横幅：`status != active` 且已过 `offline_grace_until`**

- [ ] **Step 3: 禁用按钮：新建总结、新建发布、扫码绑号（前端 + 402 双保险）**

- [ ] **Step 4: 手动测试：把 `entitlements.json` 改为过期 → 验证软限制**

- [ ] **Step 5: Commit**

```bash
git add api/routes/ static/
git commit -m "feat(entitlements): expired subscription soft-limit UI"
```

**P5 Gate / MVP 可收费节点:** P1 + P3 + P5 全部通过。

---

## Phase P6 — 公开发布（本计划附录，可并行排期）

> 不在 MVP 阻塞路径；完成后可公开发布。

| Task | 内容 |
|------|------|
| 20 | NSIS/Inno Setup 安装器 + 代码签名 |
| 21 | Tauri updater + GitHub Releases |
| 22 | Stripe / 微信支付接入 |
| 23 | `cloud/` 生产部署（TLS、备份、监控） |

---

## Spec 覆盖自检

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §3 总体架构 | Task 5–7, 9–13 |
| §4 桌面客户端 | Task 5–8 |
| §5 轻量云 | Task 9–12 |
| §6 配置云同步 | Task 14–16 |
| §7 订阅 Entitlements | Task 12, 17–19 |
| §8 安全边界 | Task 15 sanitizer, Task 13 keyring |
| §9 代码改造 | Task 1–4, 17–18 |
| §10 分阶段 P0–P5 | Phase P0–P5 |
| §12 测试策略 | 各 Task 内 pytest |

无遗漏 Blocking 项（sanitizer、.env 不上云、冲突策略均已覆盖）。

---

## 执行顺序总览

```
P0 (Task 1-4) → P1 (Task 5-7) → P2 (Task 8) [可与 P3 并行]
                              ↘
P3 (Task 9-13) → P4 (Task 14-16) → P5 (Task 17-19) → P6 (Task 20-23)
```

**建议 worktree：** `desktop-cloud-subscription` 分支，P0 合并后再开 `cloud/` 子目录并行开发。

---

**Plan complete and saved to `docs/superpowers/plans/2026-09-04-desktop-cloud-subscription.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — 每个 Task 派生子 agent，Task 间做 review，迭代快

**2. Inline Execution** — 在本会话按 Task 顺序直接实现，每 Phase 结束设检查点

**Which approach?**
