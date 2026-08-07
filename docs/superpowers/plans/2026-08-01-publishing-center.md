# 自媒体发布中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AINews 本地工具中新增发布子系统：视频号扫码登录、半自动确认发布、任务队列与 worker 上传，复用现有 AI 文案与成片输出。

**Architecture:** 与 `ingestion` 平行的垂直切片——`publish-worker` 独占 Playwright；`web_server` 仅读写 SQLite；`PlatformAdapter` 插件化，V1 仅 `WechatChannelsAdapter`；共用 `data/ainews.db`（WAL）。

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2.x · SQLite WAL · Playwright · APScheduler · Vanilla JS · AES-256-GCM（`cryptography`）

**Spec:** [docs/superpowers/specs/2026-08-01-publishing-center-design.md](../specs/2026-08-01-publishing-center-design.md) v1.1

## Global Constraints

- V1 平台：**仅 `wechat_channels`**；抖音/小红书/快手仅 YAML `enabled: false`，**不创建 stub `.py`**
- 发布模式：**半自动**；禁止成片后自动发布、禁止定时发布、禁止批量多账号
- 部署：**本地单人工具**；无用户鉴权
- **所有 Playwright 必须在 `publish-worker` 内**；`web_server` **禁止** `playwright.chromium.launch`
- `video_path` 白名单：`data/videos/*.mp4`；`cover_path` 白名单：`data/publish/covers/`
- 任务：`pending → uploading → published|failed`；条件 claim；`recover_stale_publish_jobs`；复用 `services/ingestion/db_retry.py`
- `retry_count` 上限 **3**；仅用户手动 `POST /retry`
- 上传超时默认 **600s**；QR 超时 **120s**；uploading 僵死 **45min**
- `POST /jobs` 前必须 `forbidden_words` 合规检查
- worker heartbeat：每 **30s** touch `data/publish/worker_heartbeat`
- 浏览器互斥：文件锁 `data/.playwright.lock`，等待最多 **120s**

---

## File Map（创建 / 修改一览）

| 文件 | 职责 |
|------|------|
| `scripts/spike_wechat_channels_publish.py` | Phase 0 门禁：扫码 + 上传探针 |
| `docs/publishing/wechat_channels_selectors.md` | Spike 产出：DOM 选择器文档 |
| `config/publishing_platforms.yaml` | 平台配置 |
| `src/db/models/publishing.py` | ORM 四表 |
| `src/db/engine.py` | `init_db` 注册 publishing 模型 |
| `services/publishing/path_guard.py` | 路径白名单 |
| `services/publishing/session_store.py` | 会话加解密 |
| `services/publishing/metadata_bridge.py` | AI 文案 → 发布字段 |
| `services/publishing/compliance.py` | 发布前合规 |
| `services/publishing/job_recovery.py` | 僵死任务回收 |
| `services/publishing/browser_lock.py` | Playwright 文件锁 |
| `services/publishing/registry.py` | YAML + Adapter 注册 |
| `services/publishing/adapters/base.py` | `PlatformAdapter` ABC |
| `services/publishing/adapters/wechat_channels.py` | V1 平台实现 |
| `services/publishing/qr_login.py` | QR 状态机（worker 调用） |
| `services/publishing/orchestrator.py` | 发布编排 |
| `services/publishing/worker.py` | 独立 worker 入口 |
| `api/schemas/publishing_models.py` | Pydantic 模型 |
| `api/routes/publishing_routes.py` | REST API |
| `web_server.py` | 注册 publishing router |
| `api/routes/main_routes.py` | `/publish-center` 页面路由 |
| `static/publish_center.html` | 发布中心页 |
| `static/js/publish_center/*.js` | 发布中心逻辑 |
| `static/js/shared/publish_modal.js` | 可复用发布弹窗 |
| `static/index.html` + `static/js/index/main.js` | 成片后「发布」按钮 |
| `scripts/run_publish_worker.bat` | Windows 启动 worker |
| `requirements.txt` | 添加 `cryptography`（若尚未存在） |
| `tests/test_publishing_*.py` | 单元 / API 测试 |

---

## Phase 0 — 视频号 Spike（门禁，必须先完成）

### Task 1: 视频号 Playwright Spike

**Files:**
- Create: `scripts/spike_wechat_channels_publish.py`
- Create: `docs/publishing/wechat_channels_selectors.md`
- Test: 手动 E2E（无自动化测试）

**Interfaces:**
- Produces: `docs/publishing/wechat_channels_selectors.md` 中记录的 `login_url`、`creator_url`、QR 选择器、上传 input 选择器、标题/描述/发布按钮选择器、成功判定条件

- [ ] **Step 1: 创建 Spike 脚本骨架**

```python
# scripts/spike_wechat_channels_publish.py
"""Phase 0 gate: WeChat Channels QR login + manual upload probe."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
LOGIN_URL = "https://channels.weixin.qq.com/login.html"
CREATOR_URL = "https://channels.weixin.qq.com/platform/post/create"
SESSION_OUT = ROOT / "data" / "publish" / "spike_storage_state.json"
SELECTORS_DOC = ROOT / "docs" / "publishing" / "wechat_channels_selectors.md"


def login_and_save_state(headless: bool = False) -> Path:
    SESSION_OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("请在浏览器中扫码登录，登录成功后按 Enter…")
        input()
        context.storage_state(path=str(SESSION_OUT))
        browser.close()
    return SESSION_OUT


def upload_video(session_path: Path, video_path: Path, title: str) -> dict:
    # TODO: Spike 阶段填入真实选择器（见 selectors.md）
    raise NotImplementedError("Fill selectors after first manual probe")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--title", default=f"AINews Spike {datetime.now():%Y%m%d_%H%M}")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--login-only", action="store_true")
    args = parser.parse_args()
    if not args.video.exists():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 1
    session = login_and_save_state(headless=args.headless)
    if args.login_only:
        print(f"Session saved: {session}")
        return 0
    result = upload_video(session, args.video, args.title)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 手动运行登录探针**

```bash
python scripts/spike_wechat_channels_publish.py --video data/videos/某个已有.mp4 --login-only
```

Expected: 浏览器打开视频号登录页；扫码后 `data/publish/spike_storage_state.json` 生成。

- [ ] **Step 3: 手工探测上传流程并填写 selectors 文档**

在 `docs/publishing/wechat_channels_selectors.md` 记录：

```markdown
# 微信视频号创作者中心选择器（Spike 产出）

> 探测日期：YYYY-MM-DD
> 登录 URL：https://channels.weixin.qq.com/login.html
> 投稿 URL：https://channels.weixin.qq.com/platform/post/create

## 登录
- QR 容器：`...`
- 登录成功判定：`...`

## 上传
- 文件 input：`input[type="file"]` 或 `...`
- 标题输入：`...`
- 描述输入：`...`
- 发布按钮：`...`
- 成功判定：`...`

## 限制
- 标题最大字数：...
- 标签规则：...

## 会话
- 观察有效期：... 天
```

- [ ] **Step 4: 实现 `upload_video` 并完成一次真实上传**

在 Spike 脚本中填入选择器，运行：

```bash
python scripts/spike_wechat_channels_publish.py --video data/videos/xxx.mp4 --title "Spike测试"
```

Expected: 视频号创作者中心出现新稿件（或进入审核中）。

- [ ] **Step 5: 门禁确认**

在 selectors 文档末尾写 `Gate: PASS` 或 `Gate: FAIL`。**FAIL 时不进入 Phase 1。**

---

## Phase 1 — MVP

### Task 2: Publishing ORM 模型

**Files:**
- Create: `src/db/models/publishing.py`
- Modify: `src/db/engine.py`（`init_db` import publishing）
- Test: `tests/test_publishing_models.py`

**Interfaces:**
- Produces: `PublisherAccount`, `PublishJob`, `PublishLog`, `QrLoginSession` ORM 类

- [ ] **Step 1: 写失败测试**

```python
# tests/test_publishing_models.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.engine import Base
from src.db.models.publishing import PublisherAccount, PublishJob


def test_publish_job_defaults():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    account = PublisherAccount(
        id="acc1",
        platform="wechat_channels",
        nickname="测试号",
        platform_uid="uid1",
        session_path="data/publish/sessions/acc1.enc",
    )
    session.add(account)
    job = PublishJob(id="job1", account_id="acc1", video_path="data/videos/a.mp4", title="标题")
    session.add(job)
    session.commit()
    row = session.get(PublishJob, "job1")
    assert row.status == "pending"
    assert row.retry_count == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_publishing_models.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现 ORM**

```python
# src/db/models/publishing.py
"""ORM models for publishing subsystem."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.engine import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class PublisherAccount(Base):
    __tablename__ = "publisher_accounts"
    __table_args__ = (UniqueConstraint("platform", "platform_uid", name="uq_platform_uid"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    platform_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    session_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_publish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("publisher_accounts.id"))
    video_path: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    cover_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    platform_post_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublishLog(Base):
    __tablename__ = "publish_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("publish_jobs.id"))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text, default="")
    screenshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QrLoginSession(Base):
    __tablename__ = "qr_login_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), default="create")
    account_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    qr_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: 修改 `init_db`**

在 `src/db/engine.py` 的 `init_db()` 内追加：

```python
import src.db.models.publishing  # noqa: F401
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/test_publishing_models.py -v
```

Expected: PASS

---

### Task 3: path_guard 路径白名单

**Files:**
- Create: `services/publishing/path_guard.py`
- Test: `tests/test_publishing_path_guard.py`

**Interfaces:**
- Produces: `resolve_video_path(raw: str) -> Path`, `resolve_cover_path(raw: str | None) -> Path | None`, `to_relative_posix(path: Path) -> str`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_publishing_path_guard.py
import pytest
from pathlib import Path

from services.publishing.path_guard import resolve_video_path, PathGuardError
from src.utils.config import Config


def test_resolve_video_path_accepts_data_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    video_dir = tmp_path / "data" / "videos"
    video_dir.mkdir(parents=True)
    video = video_dir / "a.mp4"
    video.write_bytes(b"\x00")
    resolved = resolve_video_path("/data/videos/a.mp4")
    assert resolved == video.resolve()


def test_resolve_video_path_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    (tmp_path / "data" / "videos").mkdir(parents=True)
    with pytest.raises(PathGuardError):
        resolve_video_path("../../etc/passwd")
```

- [ ] **Step 2: 运行确认 FAIL**

```bash
pytest tests/test_publishing_path_guard.py -v
```

- [ ] **Step 3: 实现**

```python
# services/publishing/path_guard.py
from __future__ import annotations

from pathlib import Path

from src.utils.config import Config


class PathGuardError(ValueError):
    pass


def _root() -> Path:
    return Config.ROOT_DIR.resolve()


def resolve_video_path(raw: str) -> Path:
    cleaned = (raw or "").strip().lstrip("/").replace("\\", "/")
    candidate = (_root() / cleaned).resolve()
    allowed = (_root() / "data" / "videos").resolve()
    if allowed not in candidate.parents and candidate != allowed:
        raise PathGuardError(f"video_path 不在允许目录: {raw}")
    if candidate.suffix.lower() != ".mp4":
        raise PathGuardError("video_path 必须是 .mp4")
    if not candidate.is_file():
        raise PathGuardError(f"视频文件不存在: {candidate}")
    return candidate


def resolve_cover_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    cleaned = raw.strip().lstrip("/").replace("\\", "/")
    candidate = (_root() / cleaned).resolve()
    allowed = (_root() / "data" / "publish" / "covers").resolve()
    allowed.parent.mkdir(parents=True, exist_ok=True)
    if allowed not in candidate.parents and candidate != allowed:
        raise PathGuardError(f"cover_path 不在允许目录: {raw}")
    if not candidate.is_file():
        raise PathGuardError(f"封面文件不存在: {candidate}")
    return candidate


def to_relative_posix(path: Path) -> str:
    return path.resolve().relative_to(_root()).as_posix()
```

- [ ] **Step 4: 运行测试 PASS**

```bash
pytest tests/test_publishing_path_guard.py -v
```

---

### Task 4: session_store 会话加解密

**Files:**
- Create: `services/publishing/session_store.py`
- Modify: `requirements.txt`（确保有 `cryptography`）
- Test: `tests/test_publishing_session_store.py`

**Interfaces:**
- Produces: `encrypt_bytes(data: bytes) -> bytes`, `decrypt_bytes(blob: bytes) -> bytes`, `save_encrypted(path: Path, plaintext: bytes)`, `load_encrypted(path: Path) -> bytes`, `get_session_key() -> bytes`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_publishing_session_store.py
from pathlib import Path

from services.publishing.session_store import encrypt_bytes, decrypt_bytes, save_encrypted, load_encrypted


def test_roundtrip(tmp_path, monkeypatch):
  key_file = tmp_path / "data" / "publish" / ".session_key"
  key_file.parent.mkdir(parents=True)
  key_file.write_bytes(b"a" * 32)
  monkeypatch.setenv("PUBLISH_SESSION_KEY", "")
  from src.utils.config import Config
  monkeypatch.setattr("services.publishing.session_store._KEY_FILE", key_file)

  plain = b'{"cookies":[]}'
  blob = encrypt_bytes(plain)
  out = tmp_path / "sess.enc"
  save_encrypted(out, plain)
  assert load_encrypted(out) == plain
  assert decrypt_bytes(blob) == plain
```

- [ ] **Step 2–4: 实现 `session_store.py`**

使用 `cryptography.hazmat.primitives.ciphers.aead.AESGCM`；密钥优先 `PUBLISH_SESSION_KEY`（hex 或 utf-8 32 字节），否则读/写 `data/publish/.session_key`（`os.urandom(32)`）。

文件格式：`nonce(12) + ciphertext`。

- [ ] **Step 5: 运行测试 PASS**

```bash
pytest tests/test_publishing_session_store.py -v
```

---

### Task 5: metadata_bridge 文案映射

**Files:**
- Create: `services/publishing/metadata_bridge.py`
- Test: `tests/test_publishing_metadata_bridge.py`

**Interfaces:**
- Produces: `PublishDraftMetadata` dataclass, `draft_to_publish_fields(draft, *, max_title_length=30, max_tags=10) -> dict`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_publishing_metadata_bridge.py
from services.publishing.metadata_bridge import PublishDraftMetadata, draft_to_publish_fields


def test_draft_maps_title_description_tags():
    draft = PublishDraftMetadata(
        main_line1="突发！",
        main_line2="网友：厉害了",
        sub_title="轻观点收尾",
        praise_tags=["AI", "大模型"],
    )
    out = draft_to_publish_fields(draft, max_title_length=30, max_tags=10)
    assert out["title"] == "突发！网友：厉害了"
    assert out["description"] == "轻观点收尾"
    assert out["tags"] == ["AI", "大模型"]
```

- [ ] **Step 2–4: 实现**

```python
# services/publishing/metadata_bridge.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PublishDraftMetadata:
    main_line1: str = ""
    main_line2: str = ""
    sub_title: str = ""
    sub_title2: str = ""
    praise_tags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_type: str | None = None
    source_id: str | None = None


def draft_to_publish_fields(
    draft: PublishDraftMetadata,
    *,
    max_title_length: int = 30,
    max_tags: int = 10,
) -> dict:
    title = " ".join(part for part in [draft.main_line1.strip(), draft.main_line2.strip()] if part)
    title = title[:max_title_length]
    description = (draft.sub_title or draft.sub_title2 or "").strip()
    tag_source = draft.praise_tags or draft.tags
    seen: set[str] = set()
    tags: list[str] = []
    for item in tag_source:
        t = str(item).strip()
        if t and t not in seen:
            seen.add(t)
            tags.append(t)
        if len(tags) >= max_tags:
            break
    return {"title": title, "description": description, "tags": tags}
```

- [ ] **Step 5: pytest PASS**

---

### Task 6: job_recovery 僵死回收

**Files:**
- Create: `services/publishing/job_recovery.py`
- Test: `tests/test_publishing_job_recovery.py`

**Interfaces:**
- Produces: `recover_stale_publish_jobs(session, *, stale_minutes=45) -> int`, `recover_stale_qr_sessions(session, *, stale_minutes=5) -> int`

- [ ] **Step 1: 镜像 `tests/test_ingestion_job_recovery.py` 写 uploading 僵死测试**

- [ ] **Step 2: 实现**

```python
# services/publishing/job_recovery.py
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from src.db.models.publishing import PublishJob, QrLoginSession

def recover_stale_publish_jobs(session: Session, *, stale_minutes: int = 45) -> int:
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=stale_minutes)
    updated = 0
    for job in session.query(PublishJob).filter_by(status="uploading").all():
        anchor = job.started_at or job.created_at
        if anchor and anchor < cutoff:
            job.status = "failed"
            job.finished_at = now
            job.error_message = job.error_message or "任务超时或 worker 未运行，已自动回收"
            updated += 1
    if updated:
        session.commit()
    return updated


def recover_stale_qr_sessions(session: Session, *, stale_minutes: int = 5) -> int:
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=stale_minutes)
    updated = 0
    for row in session.query(QrLoginSession).filter(
        QrLoginSession.status.in_(["pending", "processing", "waiting_scan", "scanned"])
    ):
        anchor = row.started_at or row.created_at
        if anchor and anchor < cutoff:
            row.status = "expired"
            row.finished_at = now
            row.error_message = row.error_message or "扫码会话超时"
            updated += 1
    if updated:
        session.commit()
    return updated
```

- [ ] **Step 3: pytest PASS**

---

### Task 7: browser_lock 文件互斥

**Files:**
- Create: `services/publishing/browser_lock.py`
- Test: `tests/test_publishing_browser_lock.py`

**Interfaces:**
- Produces: `browser_lock(timeout_sec: float = 120.0)` context manager

- [ ] **Step 1–4:** 使用 `filelock.FileLock`（若项目无则 `pip install filelock` 写入 requirements）锁定 `Config.ROOT_DIR / "data" / ".playwright.lock"`。

- [ ] **Step 5: pytest PASS**

---

### Task 8: registry + 平台 YAML + Adapter 基类

**Files:**
- Create: `config/publishing_platforms.yaml`（按 spec §5.1）
- Create: `services/publishing/adapters/base.py`
- Create: `services/publishing/registry.py`
- Test: `tests/test_publishing_registry.py`

**Interfaces:**
- Produces: `load_publishing_yaml() -> dict`, `get_platform_config(platform_id: str) -> dict`, `get_adapter(platform_id: str) -> PlatformAdapter`
- Produces: `PublishPayload`, `PublishResult`, `QrLoginResult`, `SessionStatus` dataclasses in `base.py`

```python
# services/publishing/adapters/base.py 核心签名
@dataclass
class PublishPayload:
    video_path: Path
    title: str
    description: str | None
    tags: list[str]
    cover_path: Path | None

@dataclass
class PublishResult:
    success: bool
    platform_post_id: str | None = None
    error_message: str | None = None

class PlatformAdapter(ABC):
    platform_id: str
    display_name: str

    def run_qr_login_flow(self, ctx: QrLoginContext) -> QrLoginResult: ...
    def validate_session(self, session_path: Path) -> SessionStatus: ...
    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult: ...
```

```python
# services/publishing/registry.py
ADAPTER_CLASSES = {
    "wechat_channels": "WechatChannelsAdapter",  # lazy import
}
```

- [ ] **测试:** `enabled: false` 平台 `get_adapter` 抛 `PlatformDisabledError`；`wechat_channels` 返回类。

---

### Task 9: WechatChannelsAdapter

**Files:**
- Create: `services/publishing/adapters/wechat_channels.py`
- Depends on: `docs/publishing/wechat_channels_selectors.md`（Task 1 产出）

**Interfaces:**
- Consumes: Spike 文档中的选择器常量
- Produces: `WechatChannelsAdapter.run_qr_login_flow`, `.publish_video`

- [ ] **Step 1:** 将 Spike 脚本中的登录/上传逻辑迁移到 Adapter（同步 API，供 worker 在线程池调用）
- [ ] **Step 2:** `publish_video` 使用 `browser_lock` + `session_store.load_encrypted` 加载 `storage_state`
- [ ] **Step 3:** 失败时截图到 `data/publish/screenshots/{job_id}.png`
- [ ] **Step 4:** 手动 E2E：通过 worker 或临时脚本验证 Adapter 独立可上传

---

### Task 10: qr_login + orchestrator

**Files:**
- Create: `services/publishing/qr_login.py`
- Create: `services/publishing/orchestrator.py`

**Interfaces:**
- `qr_login.py`: `process_qr_session(session_factory, session_id: str) -> None` — worker 调用
- `orchestrator.py`: `PublishOrchestrator.publish_job(session, job_id: str) -> PublishResult`

`process_qr_session` 流程：
1. claim `qr_login_sessions` → `processing`
2. adapter.run_qr_login_flow（循环写 `qr_image_path`、`status`）
3. `confirmed` → encrypt storage → INSERT/UPDATE `publisher_accounts`
4. `refresh` purpose → 覆盖原 `session_path`

`PublishOrchestrator.publish_job`：
1. 加载 account + decrypt session
2. `adapter.publish_video`
3. 写 `publish_logs`、更新 job 状态

---

### Task 11: publish-worker

**Files:**
- Create: `services/publishing/worker.py`
- Create: `scripts/run_publish_worker.bat`
- Mirror: `services/ingestion/worker.py`

**Interfaces:**
- Consumes: `recover_stale_*`, `process_qr_session`, `PublishOrchestrator`, `run_with_sqlite_retry`, `browser_lock`

- [ ] **Step 1: 实现 PublishWorker**

```python
# services/publishing/worker.py 核心 poll 逻辑
def poll(self) -> None:
    self._touch_heartbeat()
    with self.session_factory() as session:
        recover_stale_publish_jobs(session)
        recover_stale_qr_sessions(session)
    qr_id = self._claim_pending_qr()
    if qr_id:
        process_qr_session(self.session_factory, qr_id)
        return
    job_id = self._claim_pending_job()
    if job_id:
        with browser_lock():
            PublishOrchestrator(self.session_factory).publish_job(job_id)
```

- [ ] **Step 2:** APScheduler `interval` 5s, `max_instances=1`
- [ ] **Step 3:** `_touch_heartbeat()` 写 `data/publish/worker_heartbeat`（mtime）
- [ ] **Step 4:** `scripts/run_publish_worker.bat` 内容：

```bat
@echo off
cd /d %~dp0..
python -m services.publishing.worker
pause
```

- [ ] **Step 5:** 手动启动 worker，确认 heartbeat 文件更新

---

### Task 12: compliance 发布前检查

**Files:**
- Create: `services/publishing/compliance.py`
- Test: `tests/test_publishing_compliance.py`

**Interfaces:**
- Produces: `validate_publish_payload(title, description, tags) -> ComplianceResult`

```python
# services/publishing/compliance.py
from utils.forbidden_words import scan_content_fields, partition_violations

def validate_publish_payload(title: str, description: str | None, tags: list[str]):
    fields = {
        "main_line1": title,
        "sub_title": description or "",
        "tags": " ".join(tags),
    }
    violations = scan_content_fields(fields)
    errors, _ = partition_violations(violations)
    return len(errors) == 0, violations
```

- [ ] pytest PASS

---

### Task 13: API schemas + routes

**Files:**
- Create: `api/schemas/publishing_models.py`
- Create: `api/routes/publishing_routes.py`
- Modify: `web_server.py`
- Test: `tests/test_publishing_api.py`

**Interfaces:**
- Router prefix: `/api/publishing`
- **禁止** 任何 Playwright import

关键端点实现要点：

| 端点 | 逻辑 |
|------|------|
| `POST /accounts/qr-start` | 校验 platform enabled → INSERT `qr_login_sessions` |
| `GET /accounts/qr-status/{id}` | 返回 status + `/data/publish/qr/{id}.png` URL |
| `POST /jobs` | path_guard + compliance + account active → INSERT job |
| `POST /jobs/{id}/retry` | `retry_count < 3` 且 status=failed → pending |
| `GET /health` | 读 heartbeat mtime；统计 pending_jobs |

```python
# web_server.py 追加
from api.routes.publishing_routes import router as publishing_router
app.include_router(publishing_router)
```

- [ ] **API 测试（镜像 test_ingestion_api.py）**

```python
def test_qr_start_rejects_disabled_platform(client):
    resp = client.post("/api/publishing/accounts/qr-start", json={"platform": "douyin"})
    assert resp.status_code == 400

def test_create_job_rejects_path_traversal(client):
    ...
```

```bash
pytest tests/test_publishing_api.py -v
```

---

### Task 14: 发布中心前端

**Files:**
- Create: `static/publish_center.html`
- Create: `static/js/publish_center/init.js`, `accounts.js`, `queue.js`, `publish_form.js`
- Modify: `api/routes/main_routes.py` — `GET /publish-center`
- Modify: 各页面 `navbar` 增加「📤 发布中心」

**UI 行为:**
1. 启动时 `GET /api/publishing/health` — worker 不可达显示黄色横幅
2. 账号区：`GET /accounts` + 扫码弹窗轮询 `qr-status` 每 2s
3. 队列区：`GET /jobs` 每 5s 刷新；pending > 60s 显示「等待 worker…」
4. 快速发布：选视频（`/api/list-videos`）→ 填表 → `POST /jobs`

沿用 `static/css/tokens.css` 与现有 navbar 样式（参考 `static/ingestion_library.html`）。

---

### Task 15: 主页发布弹窗集成

**Files:**
- Create: `static/js/shared/publish_modal.js`
- Modify: `static/index.html` — script 引用 + navbar
- Modify: `static/js/index/main.js` — 成片成功区域加「📤 发布」按钮

```javascript
// static/js/shared/publish_modal.js 导出
export function openPublishModal({ videoPath, draft }) {
  // 渲染模态框；预填 title/description/tags
  // 确认时 POST /api/publishing/jobs
}
```

在 `main.js` 成片成功回调中：

```javascript
const draft = {
  main_line1: document.getElementById('editableMainLine1')?.value || '',
  main_line2: document.getElementById('editableMainLine2')?.value || '',
  sub_title: document.getElementById('editableSubTitle')?.value || '',
  praise_tags: window.lastSummaryData?.praise_tags || [],
  tags: window.lastSummaryData?.tags || [],
};
openPublishModal({ videoPath: result.video_path, draft });
```

保存 `lastSummaryData` 于 `generate-summary` 成功回调。

- [ ] 手动 E2E：主页成片 → 发布弹窗 → 确认 → 队列 pending → worker 上传

---

### Task 16: 封面截取 API

**Files:**
- Modify: `api/routes/publishing_routes.py` — `POST /extract-cover`
- Reuse: `api/routes/video_routes.py` 中 cv2 截帧逻辑（抽取小函数或内联）

```python
@router.post("/extract-cover")
async def extract_cover(body: ExtractCoverRequest):
    video = resolve_video_path(body.video_path)
    out_dir = Config.ROOT_DIR / "data" / "publish" / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video.stem}_cover.jpg"
    # cv2.VideoCapture 读首帧 → cv2.imwrite
    return {"success": True, "cover_path": to_relative_posix(out_path)}
```

---

## Phase 2 — 体验打磨（MVP 后）

### Task 17: 其余页面集成发布弹窗
- `video_maker.html` / `github_video_maker.html` 引入 `publish_modal.js`

### Task 18: 共享导航 `static/js/shared/nav.js`
- 减少各 HTML navbar 重复

### Task 19: 失败截图 UI
- 队列展开显示 `publish_logs.screenshot_path` 缩略图

### Task 20: 抽取 `BrowserLauncher`
- 从 `CrawlerService` / publishing adapter 共用 Playwright 启动参数

---

## Spec Coverage Self-Review

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §3 Playwright 仅 worker | Task 11, 13（API 无 Playwright） |
| §6 QR 状态机 | Task 2, 10, 11 |
| §6.3 会话加密 | Task 4 |
| §6.4 browser_lock | Task 7, 9, 11 |
| §7 job claim + recovery | Task 6, 11 |
| §7.4 metadata_bridge | Task 5, 15 |
| §8 SQLite 模型 | Task 2 |
| §9 API + path_guard + compliance | Task 3, 12, 13, 16 |
| §9.4 health/heartbeat | Task 11, 13, 14 |
| §10 前端 | Task 14, 15 |
| §13 Phase 0 Spike | Task 1 |
| §13 Phase 1 MVP | Task 2–16 |
| §13 Phase 2 | Task 17–20 |
| 预留三平台无 stub | Task 8（仅 YAML） |

无 TBD / 占位符步骤。

---

## 验证清单（Phase 1 完成标准）

```bash
# 单元测试
pytest tests/test_publishing_*.py -v

# 启动双进程
python web_server.py
python -m services.publishing.worker

# 手动 E2E
# 1. /publish-center → 添加视频号 → 扫码成功
# 2. 主页成片 → 发布 → 确认
# 3. 队列显示 published；视频号后台可见新稿
```

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-01 | 初版实施计划（Phase 0–1 详细，Phase 2 概要） |
