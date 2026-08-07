# 多平台账号管理（抖音 / 快手 / 小红书）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在发布中心为抖音、快手、小红书增加扫码账号管理（登录 / 刷新 / 删除 / 分组展示），复用现有 `PlatformAdapter` 与内嵌 worker；本阶段不实现三平台自动发视频。

**Architecture:** 抽取 `qr_helpers.py` 共享扫码逻辑；每平台一个 Adapter；YAML `capabilities` 区分 `account_login` 与 `video_publish`；DB 不改表；Playwright 仅在内嵌 worker 中运行。

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy · Playwright · AES 会话加密 · Vanilla JS

**Spec:** [docs/superpowers/specs/2026-08-05-multi-platform-account-management-design.md](../specs/2026-08-05-multi-platform-account-management-design.md)

## Global Constraints

- 本阶段范围：**仅账号管理**；`video_publish: false` 的平台禁止 `POST /jobs`
- 本地单人工具；半自动；扫码登录；无官方 OAuth
- Playwright **仅**在内嵌 worker（`PUBLISH_WORKER_MODE=embedded` 默认）中运行
- 同一时刻仅 1 个 QR 浏览器任务；复用 `browser_lock`
- 会话加密：`data/publish/sessions/{account_id}.enc`
- 实施顺序 Spike 门禁：**抖音 → 快手 → 小红书**
- 每平台 Spike 未 `Gate: PASS` 前，YAML 该平台 `enabled: false`
- 不改 `publisher_accounts` 等 ORM schema

---

## File Map

| 文件 | 职责 |
|------|------|
| `services/publishing/adapters/qr_helpers.py` | `QrLoginProfile` + `run_generic_qr_login` |
| `services/publishing/adapters/base.py` | 增加 `persist_storage_state` 默认实现 |
| `services/publishing/adapters/wechat_channels.py` | 重构为调用 `qr_helpers` |
| `services/publishing/adapters/douyin.py` | 抖音 Adapter |
| `services/publishing/adapters/kuaishou.py` | 快手 Adapter |
| `services/publishing/adapters/xiaohongshu.py` | 小红书 Adapter |
| `services/publishing/adapters/publish_stubs.py` | 共享 `publish_not_implemented()` |
| `services/publishing/registry.py` | `build_adapter()` + 四平台注册 |
| `services/publishing/platform_capabilities.py` | 读 YAML capabilities / limits |
| `services/publishing/qr_login.py` | 去除 `WechatChannelsAdapter` 硬编码 |
| `config/publishing_platforms.yaml` | v2 + capabilities + qr_profile |
| `api/routes/publishing_routes.py` | capabilities 校验、`GET /accounts` 增强 |
| `static/publish_center.html` | 平台分组 + 四平台添加下拉 |
| `static/js/shared/publish_modal.js` | 仅 `video_publish` 账号 |
| `scripts/spike_*_login.py` | 三平台 Spike |
| `docs/publishing/*_selectors.md` | Spike 产出 |
| `tests/test_publishing_*.py` | 单元 / API 测试 |

---

## Phase 2A-0 — 基础设施

### Task 1: `QrLoginProfile` + `run_generic_qr_login`

**Files:**
- Create: `services/publishing/adapters/qr_helpers.py`
- Test: `tests/test_publishing_qr_helpers.py`

**Interfaces:**
- Produces: `QrLoginProfile`, `run_generic_qr_login(profile, ctx, *, headless=False) -> QrLoginResult`
- Produces: `is_login_success_url(url: str, success_url_excludes: list[str]) -> bool`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_publishing_qr_helpers.py
from services.publishing.adapters.qr_helpers import is_login_success_url


def test_login_success_when_not_on_login_page():
    assert is_login_success_url(
        "https://creator.douyin.com/creator-micro/home",
        ["login", "passport"],
    )


def test_login_pending_on_login_page():
    assert not is_login_success_url(
        "https://creator.douyin.com/login",
        ["login", "passport"],
    )
```

- [ ] **Step 2: 运行确认 FAIL**

```bash
set PYTHONPATH=D:\git\AINews
pytest tests/test_publishing_qr_helpers.py -v
```

- [ ] **Step 3: 实现 `qr_helpers.py`**

```python
# services/publishing/adapters/qr_helpers.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from playwright.sync_api import sync_playwright

from services.publishing.adapters.base import AccountInfo, QrLoginContext, QrLoginResult


@dataclass
class QrLoginProfile:
    platform_id: str
    login_url: str
    success_url_excludes: list[str] = field(default_factory=lambda: ["login", "passport"])
    qr_selector: str | None = None
    headless: bool = False
    uid_extractor: Literal["dom", "generated"] = "generated"
    nickname_selector: str | None = None
    extract_account_info: Callable | None = None  # optional override


def is_login_success_url(url: str, success_url_excludes: list[str]) -> bool:
    lower = (url or "").lower()
    return not any(token in lower for token in success_url_excludes)


def run_generic_qr_login(profile: QrLoginProfile, ctx: QrLoginContext) -> QrLoginResult:
    ctx.qr_dir.mkdir(parents=True, exist_ok=True)
    qr_path = ctx.qr_dir / f"{ctx.session_id}.png"
    deadline = time.time() + ctx.qr_timeout_sec

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=profile.headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(profile.login_url or ctx.login_url, wait_until="domcontentloaded")
        _capture_qr(page, qr_path, profile.qr_selector)

        while time.time() < deadline:
            if is_login_success_url(page.url, profile.success_url_excludes):
                storage = context.storage_state()
                browser.close()
                info = _resolve_account_info(page, profile)
                return QrLoginResult(
                    status="confirmed",
                    qr_image_path=str(qr_path),
                    account_info=info,
                    storage_state_json=json.dumps(storage).encode("utf-8"),
                )
            page.wait_for_timeout(2000)
            _capture_qr(page, qr_path, profile.qr_selector)

        browser.close()
        return QrLoginResult(
            status="expired",
            qr_image_path=str(qr_path),
            error_message=f"扫码超时（{ctx.qr_timeout_sec}s）",
        )


def _capture_qr(page, qr_path: Path, selector: str | None) -> None:
    if selector:
        page.locator(selector).first.screenshot(path=str(qr_path))
    else:
        page.screenshot(path=str(qr_path), full_page=True)


def _resolve_account_info(page, profile: QrLoginProfile) -> AccountInfo:
    if profile.extract_account_info:
        return profile.extract_account_info(page)
    nickname = "未命名账号"
    if profile.nickname_selector:
        try:
            nickname = page.locator(profile.nickname_selector).first.inner_text(timeout=3000).strip()
        except Exception:
            pass
    uid = f"{profile.platform_id}_{int(time.time())}"
    return AccountInfo(nickname=nickname or "未命名账号", platform_uid=uid)
```

- [ ] **Step 4: pytest PASS**

---

### Task 2: 基类 `persist_storage_state` + 去硬编码

**Files:**
- Modify: `services/publishing/adapters/base.py`
- Modify: `services/publishing/qr_login.py:103-106`
- Modify: `services/publishing/adapters/wechat_channels.py`（删除静态 `persist_storage_state` 若存在）
- Test: `tests/test_publishing_qr_login_upsert.py`

**Interfaces:**
- Produces: `PlatformAdapter.persist_storage_state(dest: Path, storage_state_json: bytes)`

- [ ] **Step 1: 在 `base.py` 增加默认方法**

```python
from pathlib import Path
from services.publishing.session_store import save_encrypted

class PlatformAdapter(ABC):
    ...
    def persist_storage_state(self, dest: Path, storage_state_json: bytes) -> None:
        save_encrypted(dest, storage_state_json)
```

- [ ] **Step 2: 修改 `_upsert_account`**

```python
# services/publishing/qr_login.py
adapter = get_adapter(platform)
session_path = Config.ROOT_DIR / "data" / "publish" / "sessions" / f"{account.id}.enc"
adapter.persist_storage_state(session_path, storage_state_json)
```

- [ ] **Step 3: 写测试**（mock `get_adapter` 断言 `persist_storage_state` 被调用）

- [ ] **Step 4: pytest PASS**

---

### Task 3: `platform_capabilities.py` + YAML v2

**Files:**
- Create: `services/publishing/platform_capabilities.py`
- Modify: `config/publishing_platforms.yaml`
- Test: `tests/test_publishing_capabilities.py`

**Interfaces:**
- Produces: `get_capabilities(platform_id) -> dict`
- Produces: `can_account_login(platform_id) -> bool`
- Produces: `can_video_publish(platform_id) -> bool`
- Produces: `get_platform_limits(platform_id) -> dict`

- [ ] **Step 1: 写失败测试**

```python
def test_wechat_can_publish():
    from services.publishing.platform_capabilities import can_video_publish
    assert can_video_publish("wechat_channels") is True


def test_douyin_cannot_publish_yet():
    from services.publishing.platform_capabilities import can_video_publish
    assert can_video_publish("douyin") is False
```

- [ ] **Step 2: 更新 YAML**（按 spec §4 完整草案；三平台初始 `enabled: false` 直至各 Spike PASS）

- [ ] **Step 3: 实现 `platform_capabilities.py`**

```python
from services.publishing.registry import get_platform_config, PlatformNotFoundError

def get_capabilities(platform_id: str) -> dict:
    cfg = get_platform_config(platform_id)
    return dict(cfg.get("capabilities") or {})

def can_account_login(platform_id: str) -> bool:
    return bool(get_capabilities(platform_id).get("account_login"))

def can_video_publish(platform_id: str) -> bool:
    return bool(get_capabilities(platform_id).get("video_publish"))
```

- [ ] **Step 4: pytest PASS**

---

### Task 4: Registry `build_adapter` 统一工厂

**Files:**
- Modify: `services/publishing/registry.py`
- Test: `tests/test_publishing_registry.py`（扩展）

**Interfaces:**
- Produces: `build_adapter(cfg: dict) -> PlatformAdapter`
- `ADAPTER_FACTORIES` 增加 douyin / kuaishou / xiaohongshu 路径（实现后可 lazy import）

- [ ] **Step 1: 实现 `build_adapter`**

```python
ADAPTER_FACTORIES = {
    "wechat_channels": "services.publishing.adapters.wechat_channels:WechatChannelsAdapter",
    "douyin": "services.publishing.adapters.douyin:DouyinAdapter",
    "kuaishou": "services.publishing.adapters.kuaishou:KuaishouAdapter",
    "xiaohongshu": "services.publishing.adapters.xiaohongshu:XiaohongshuAdapter",
}

def build_adapter(cfg: dict) -> PlatformAdapter:
    defaults = load_publishing_yaml().get("defaults") or {}
    adapter_key = cfg.get("adapter", cfg["id"])
    factory = _import_adapter_class(adapter_key)
    return factory(
        platform_id=cfg["id"],
        login_url=cfg.get("login_url", ""),
        creator_url=cfg.get("creator_url", ""),
        upload_timeout_sec=int(defaults.get("upload_timeout_sec", 600)),
        qr_profile=cfg.get("qr_profile") or {},
        limits=cfg.get("limits") or {},
    )

def get_adapter(platform_id: str) -> PlatformAdapter:
    cfg = get_platform_config(platform_id)
    if not cfg.get("enabled", False):
        raise PlatformDisabledError(f"平台未启用: {platform_id}")
    return build_adapter(cfg)
```

- [ ] **Step 2: 调整 `WechatChannelsAdapter.__init__` 签名对齐**（`platform_id`, `qr_profile`, `limits`）

- [ ] **Step 3: pytest PASS**

---

### Task 5: 共享 `publish_not_implemented` stub

**Files:**
- Create: `services/publishing/adapters/publish_stubs.py`

```python
from pathlib import Path
from services.publishing.adapters.base import PublishPayload, PublishResult

def publish_not_implemented(session_path: Path, payload: PublishPayload) -> PublishResult:
    return PublishResult(
        success=False,
        error_message="该平台自动发布尚未开放，请在创作者中心手动上传",
        manual_publish_pending=True,
    )
```

三平台 Adapter 的 `publish_video` 本阶段直接调用此函数。

---

### Task 6: API 增强

**Files:**
- Modify: `api/routes/publishing_routes.py`
- Test: `tests/test_publishing_api.py`

- [ ] **Step 1: `POST /accounts/qr-start` 增加校验**

```python
from services.publishing.platform_capabilities import can_account_login

if not can_account_login(body.platform):
    raise HTTPException(status_code=400, detail="该平台暂不支持账号登录")
```

- [ ] **Step 2: `POST /jobs` 增加 `can_video_publish` 校验**

```python
from services.publishing.platform_capabilities import can_video_publish

cfg_platform = account.platform
if not can_video_publish(cfg_platform):
    raise HTTPException(status_code=400, detail="该平台自动发布尚未开放")
```

- [ ] **Step 3: `GET /accounts` 增强响应**

```python
{
    "id": row.id,
    "platform": row.platform,
    "platform_display_name": cfg.get("display_name"),
    "nickname": row.nickname,
    "status": row.status,
    "can_publish": can_video_publish(row.platform),
    ...
}
```

- [ ] **Step 4: `GET /platforms` 返回完整 cfg**（含 `capabilities`, `icon`, `limits`）

- [ ] **Step 5: 新增测试**

```python
def test_qr_start_rejects_platform_without_account_login(client, monkeypatch):
    # mock YAML 或 disabled platform
    ...

def test_create_job_rejects_non_publish_platform(client, ...):
    # 创建 douyin 账号后 POST /jobs 期望 400
    ...
```

- [ ] **Step 6: pytest PASS**

---

### Task 7: 重构 `WechatChannelsAdapter` 使用 `qr_helpers`

**Files:**
- Modify: `services/publishing/adapters/wechat_channels.py`
- Test: 回归 `tests/test_publishing_*.py`

- [ ] **Step 1: `run_qr_login_flow` 改为**

```python
def run_qr_login_flow(self, ctx: QrLoginContext) -> QrLoginResult:
    profile = QrLoginProfile(
        platform_id="wechat_channels",
        login_url=self.login_url,
        success_url_excludes=["login"],
        qr_selector=None,
        extract_account_info=self._extract_account_info,
    )
    return run_generic_qr_login(profile, ctx)
```

- [ ] **Step 2: 保留 `validate_session` / `publish_video` 不变**

- [ ] **Step 3: 手动 E2E** — 视频号重新扫码仍成功

---

### Task 8: 发布中心 UI — 四平台分组

**Files:**
- Modify: `static/publish_center.html`
- Modify: `static/js/shared/publish_modal.js`

- [ ] **Step 1: 加载 `/api/publishing/platforms`，构建「添加账号」下拉**

```javascript
async function loadPlatformMenu() {
    const resp = await fetch('/api/publishing/platforms');
    const data = await resp.json();
    const enabled = (data.platforms || []).filter(p => p.enabled && p.capabilities?.account_login);
    // 渲染下拉：enabled.map(p => ...)
}
```

- [ ] **Step 2: `loadAccounts` 按 `platform` 分组渲染**

```javascript
function renderAccountsGrouped(accounts, platforms) {
    const byPlatform = {};
    accounts.forEach(a => { (byPlatform[a.platform] ||= []).push(a); });
    // 每个平台一节：标题 + 卡片；卡片显示 can_publish ? '可发布' : '仅账号'
}
```

- [ ] **Step 3: 扫码弹窗标题动态化**

```javascript
document.querySelector('#qrModal h3').textContent = `扫码登录${displayName}`;
```

- [ ] **Step 4: `publish_modal.js` — `loadAccounts` 过滤**

```javascript
const accounts = (data.accounts || []).filter(a => a.status === 'active' && a.can_publish);
```

- [ ] **Step 5: 快速发布账号下拉同样过滤 `can_publish`**

---

## Phase 2A-1 — 抖音（Spike 门禁）

### Task 9: 抖音 Spike

**Files:**
- Create: `scripts/spike_douyin_login.py`
- Create: `docs/publishing/douyin_selectors.md`

- [ ] **Step 1: 脚本打开 `https://creator.douyin.com/`，等待用户扫码**

- [ ] **Step 2: 记录 QR 选择器（是否在 iframe）、成功 URL、昵称 DOM**

- [ ] **Step 3: 文档末尾写 `Gate: PASS` 或 `FAIL`**

```bash
python scripts/spike_douyin_login.py --login-only
```

**未 PASS 不进入 Task 10。**

---

### Task 10: `DouyinAdapter`

**Files:**
- Create: `services/publishing/adapters/douyin.py`
- Modify: `config/publishing_platforms.yaml` — `douyin.enabled: true`
- Test: `tests/test_publishing_douyin_adapter.py`（mock playwright 可选；至少测 profile 构建）

**Interfaces:**
- Consumes: `docs/publishing/douyin_selectors.md` 中 `success_url_excludes`, `qr_selector`, `nickname_selector`
- Produces: `DouyinAdapter.run_qr_login_flow`, `validate_session`, `publish_video` → stub

```python
# services/publishing/adapters/douyin.py
class DouyinAdapter(PlatformAdapter):
    platform_id = "douyin"
    display_name = "抖音"

    def __init__(self, *, platform_id, login_url, creator_url, upload_timeout_sec, qr_profile, limits):
        self.login_url = login_url
        self.creator_url = creator_url
        self.upload_timeout_sec = upload_timeout_sec
        self.qr_profile = qr_profile

    def run_qr_login_flow(self, ctx: QrLoginContext) -> QrLoginResult:
        profile = QrLoginProfile(
            platform_id="douyin",
            login_url=self.login_url,
            success_url_excludes=self.qr_profile.get("success_url_excludes", ["login", "passport"]),
            qr_selector=self.qr_profile.get("qr_selector"),
        )
        return run_generic_qr_login(profile, ctx)

    def validate_session(self, session_path: Path) -> SessionStatus:
        # 加载 storage_state → goto creator_url → login 在 URL 则 expired
        ...

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        return publish_not_implemented(session_path, payload)
```

- [ ] **手动 E2E:** 发布中心 → 添加抖音账号 → 扫码 → 分组列表出现昵称

---

## Phase 2A-2 — 快手（Spike 门禁）

### Task 11: 快手 Spike

**Files:**
- Create: `scripts/spike_kuaishou_login.py`
- Create: `docs/publishing/kuaishou_selectors.md`

（步骤同 Task 9，URL: `https://cp.kuaishou.com/`）

---

### Task 12: `KuaishouAdapter`

**Files:**
- Create: `services/publishing/adapters/kuaishou.py`
- Modify: `config/publishing_platforms.yaml` — `kuaishou.enabled: true`

（结构同 `DouyinAdapter`，选择器来自 `kuaishou_selectors.md`）

- [ ] **手动 E2E:** 快手账号绑定成功

---

## Phase 2A-3 — 小红书（Spike 门禁）

### Task 13: 小红书 Spike

**Files:**
- Create: `scripts/spike_xiaohongshu_login.py`
- Create: `docs/publishing/xiaohongshu_selectors.md`

- [ ] **额外验证:** 是否出现滑块；是否需 `playwright.chromium.launch(args=['--disable-blink-features=AutomationControlled'])`
- [ ] 若 Spike FAIL：文档记录降级方案（手动导出 storage_state，Phase 2A+ 再做 `POST /accounts/import-session`）

---

### Task 14: `XiaohongshuAdapter`

**Files:**
- Create: `services/publishing/adapters/xiaohongshu.py`
- Modify: `config/publishing_platforms.yaml` — `xiaohongshu.enabled: true`

```python
# 若 Spike 要求 stealth：
def _launch_browser(playwright):
    return playwright.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
```

在 `run_generic_qr_login` 可增加可选 `launch_hook` 参数（Task 1 修订时加入）。

- [ ] **手动 E2E:** 小红书账号绑定成功

---

## Phase 2A-4 — 会话验证（可选但建议）

### Task 15: `POST /accounts/{id}/validate`

**Files:**
- Modify: `api/routes/publishing_routes.py`
- Modify: `services/publishing/worker.py` — 可选：validate 队列；或 API 同步 `asyncio.to_thread(adapter.validate_session)`

简化方案（V1）：API 内联调用，不经过 worker：

```python
@router.post("/accounts/{account_id}/validate")
async def validate_account(account_id: str, db: Session = Depends(get_db)):
    row = db.get(PublisherAccount, account_id)
    ...
    adapter = get_adapter(row.platform)
    status = await asyncio.to_thread(adapter.validate_session, Config.ROOT_DIR / row.session_path)
    row.status = "active" if status == "active" else "expired"
    db.commit()
    return {"success": True, "status": row.status}
```

- [ ] 发布中心账号卡片增加「检测登录状态」按钮

---

## Spec Coverage Self-Review

| Spec 章节 | Task |
|-----------|------|
| §3.1 qr_helpers | Task 1, 7 |
| §3.3 capabilities | Task 3, 5, 6 |
| §3.4 Registry | Task 4 |
| §3.5 qr_login 去硬编码 | Task 2 |
| §4 YAML v2 | Task 3 |
| §6 API | Task 6, 15 |
| §7 前端 | Task 8 |
| §9 抖音/快手/小红书 | Task 9–14 |
| §14 验收标准 | 各 Task 手动 E2E |

---

## 验证清单（Phase 2A 完成）

```bash
set PYTHONPATH=D:\git\AINews
pytest tests/test_publishing_qr_helpers.py tests/test_publishing_capabilities.py tests/test_publishing_registry.py tests/test_publishing_api.py -v
```

手动：

1. 发布中心四平台均可「添加账号」（已 enabled 的平台）
2. 抖音 / 快手 / 小红书各绑定 1 个账号，刷新后仍在
3. 重新登录覆盖会话；删除清除 `.enc`
4. 发布弹窗与快速发布 **仅** 显示视频号账号
5. 对抖音账号 `POST /jobs` 返回 400
6. 视频号发布回归正常

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-05 | 初版实施计划（Phase 2A 账号管理） |
