# Token 用量统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在系统配置增加「用量统计」页，按北京时间窗汇总已配置语言模型与视觉模型的实际 token（来自 API `usage`）。

**Architecture:** 所有 `chat.completions.create` 经 `complete_chat()` 记录到 SQLite `llm_token_usage_events`；`GET /api/models/usage` 聚合；设置页新 Tab 只读展示。

**Tech Stack:** SQLAlchemy, FastAPI, pytest, 现有 settings Soft UI（无新图表库）。

**Spec:** `docs/superpowers/specs/2026-08-24-token-usage-design.md`

## Global Constraints

- Token 只取接口 `usage`，不做 tiktoken 估算、不拉厂商账单
- 记录失败不得打断业务调用
- 时间窗按 Asia/Shanghai：`today` | `7d` | `30d` | `all`
- `kind` 仅 `language` | `vision`
- 用户未要求则不 git commit
- 不提交 `config/models.local.yaml`

## File Map

- Create: `src/db/models/llm_usage.py` — ORM
- Create: `services/model_config/token_usage.py` — parse / record / query / complete_chat
- Create: `tests/test_token_usage.py` — 解析与聚合
- Create: `tests/test_token_usage_api.py` — HTTP
- Create: `static/js/settings_token_usage.js` — Tab 前端
- Modify: `src/db/engine.py` — `init_db` 注册模型
- Modify: `api/routes/model_config_routes.py` — usage 路由
- Modify: 各 `chat.completions.create` 调用点改为 `complete_chat`
- Modify: `static/settings.html`, `static/js/settings_tabs.js`, `static/css/model_settings.css`

---

### Task 1: Event table + parse/record/query

**Files:**
- Create: `src/db/models/llm_usage.py`
- Create: `services/model_config/token_usage.py`
- Modify: `src/db/engine.py`（`init_db` 增加 `import src.db.models.llm_usage`）
- Test: `tests/test_token_usage.py`

**Interfaces:**
- Produces: `parse_completion_usage(response) -> tuple[int, int, int]`
- Produces: `record_token_usage(*, kind, profile_id, provider, model, task, prompt_tokens, completion_tokens, total_tokens, session=None) -> None`
- Produces: `query_token_usage(session, *, range_key: str) -> dict`
- Produces: `clear_token_usage(session) -> int`
- Produces: `USAGE_TASK_LABELS: dict[str, str]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_token_usage.py
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from src.db.engine import Base, init_db, get_session_factory
from services.model_config.token_usage import (
    parse_completion_usage,
    record_token_usage,
    query_token_usage,
    clear_token_usage,
)


def test_parse_usage_reads_openai_shape():
    resp = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14)
    )
    assert parse_completion_usage(resp) == (10, 4, 14)


def test_parse_usage_missing_is_zero():
    assert parse_completion_usage(SimpleNamespace()) == (0, 0, 0)
    assert parse_completion_usage(SimpleNamespace(usage=SimpleNamespace())) == (0, 0, 0)


def test_parse_usage_fills_total_from_parts():
    resp = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2))
    assert parse_completion_usage(resp) == (3, 2, 5)


def test_query_usage_aggregates_by_model_and_task(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    with factory() as session:
        record_token_usage(
            kind="language",
            profile_id="p1",
            provider="deepseek",
            model="deepseek-chat",
            task="content_gen",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            session=session,
        )
        record_token_usage(
            kind="vision",
            profile_id="v1",
            provider="qwen",
            model="qwen-vl-max",
            task="image_score",
            prompt_tokens=800,
            completion_tokens=50,
            total_tokens=850,
            session=session,
        )
        session.commit()
        summary = query_token_usage(session, range_key="all")
    assert summary["totals"]["calls"] == 2
    assert summary["totals"]["total_tokens"] == 970
    assert summary["totals"]["language_tokens"] == 120
    assert summary["totals"]["vision_tokens"] == 850
    models = {row["model"]: row for row in summary["by_model"]}
    assert models["deepseek-chat"]["calls"] == 1
    tasks = {row["task"]: row for row in summary["by_task"]}
    assert tasks["image_score"]["total_tokens"] == 850


def test_clear_token_usage(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    with factory() as session:
        record_token_usage(
            kind="language",
            profile_id="p1",
            provider="deepseek",
            model="deepseek-chat",
            task="model_test",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            session=session,
        )
        session.commit()
        deleted = clear_token_usage(session)
        session.commit()
        summary = query_token_usage(session, range_key="all")
    assert deleted == 1
    assert summary["totals"]["calls"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_token_usage.py -q`

Expected: `ModuleNotFoundError: services.model_config.token_usage` 或 import 失败。

- [ ] **Step 3: Implement ORM + helpers**

`src/db/models/llm_usage.py`：

```python
"""ORM for LLM/VL token usage events."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.engine import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class LlmTokenUsageEvent(Base):
    __tablename__ = "llm_token_usage_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    task: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
```

`services/model_config/token_usage.py` 要点：

- `parse_completion_usage`：`getattr(usage, "prompt_tokens", 0) or 0` 等，total 缺省为 prompt+completion。
- `record_token_usage`：若未传 `session`，用 `session_scope()`；`try/except` 打 `logger.warning`，不抛。
- `range_key` 切窗用 `beijing_now()`：`today` = 当天 00:00 北京时间转 UTC；`7d`/`30d` = 现在减 N 天；`all` = 无下限。非法 key 抛 `ValueError`。
- `query_token_usage` 返回 spec 中的 dict；`display_name` 先等于 `model`，Task 5 再按配置补全。
- `USAGE_TASK_LABELS` 按 spec 任务字典。
- `by_model` 分组键：`(kind, profile_id, provider, model)`。
- `by_task` 分组键：`task`，带 `label`。

`init_db` 增加：

```python
import src.db.models.llm_usage  # noqa: F401
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_token_usage.py -q`

Expected: PASS

---

### Task 2: `complete_chat` wrapper

**Files:**
- Modify: `services/model_config/token_usage.py`
- Test: `tests/test_token_usage.py`（追加）

**Interfaces:**
- Consumes: `parse_completion_usage`, `record_token_usage`
- Produces: `complete_chat(client, *, kind: str, profile: dict | None, task: str, **kwargs) -> Any`

- [ ] **Step 1: Write the failing test**

```python
def test_complete_chat_records_usage(tmp_path, monkeypatch):
    from services.model_config.token_usage import complete_chat, query_token_usage

    db_path = tmp_path / "usage.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()

    class _Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=9, completion_tokens=1, total_tokens=10),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    resp = complete_chat(
        client,
        kind="language",
        profile={"id": "p1", "provider": "deepseek", "model": "deepseek-chat"},
        task="model_test",
        model="deepseek-chat",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert resp.choices[0].message.content == "ok"
    factory = get_session_factory()
    with factory() as session:
        summary = query_token_usage(session, range_key="all")
    assert summary["totals"]["total_tokens"] == 10
    assert summary["totals"]["calls"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_usage.py::test_complete_chat_records_usage -q`

Expected: FAIL `complete_chat` 未定义。

- [ ] **Step 3: Implement wrapper**

```python
def complete_chat(client, *, kind: str, profile: dict | None, task: str, **kwargs):
    response = client.chat.completions.create(**kwargs)
    prompt, completion, total = parse_completion_usage(response)
    profile = profile or {}
    record_token_usage(
        kind=kind,
        profile_id=str(profile.get("id") or "") or None,
        provider=str(profile.get("provider") or ""),
        model=str(kwargs.get("model") or profile.get("model") or ""),
        task=task,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )
    return response
```

调用失败让异常向上抛（不记事件）。记录在 `create` 成功之后。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_token_usage.py -q`

Expected: PASS

---

### Task 3: Wire language + vision call sites

**Files:**
- Modify: `services/model_config/registry.py`（`test_language_model` / `test_vision_model`）
- Modify: `services/ingestion/article_score_llm.py`
- Modify: `services/ingestion/story_cluster_llm.py`
- Modify: `services/ingestion/image_score_vl.py`
- Modify: `utils/content_compliance.py`（`_complete_json_text` 内 `create`）
- Modify: `services/content_generation_service.py`
- Modify: `utils/summary_highlights.py`
- Modify: `services/related_image_service.py`
- Modify: `api/routes/crawler_routes.py`（若仍直接 `create`）
- Test: 现有 `tests/test_content_compliance.py`、`tests/test_image_score_vl.py`、`tests/test_content_generation_service.py` 应继续绿；必要时给 mock 补 `usage`

**Interfaces:**
- Consumes: `complete_chat(client, kind=..., profile=..., task=..., **kwargs)`
- 每个调用点：能拿到 profile 的用真实 profile；`.env` 回退用 `{"id": "env_deepseek", "provider": "deepseek", "model": <实际 model>}`

- [ ] **Step 1: Replace creates (pattern)**

把：

```python
response = client.chat.completions.create(**request_kwargs)
```

改成：

```python
from services.model_config.token_usage import complete_chat

response = complete_chat(
    client,
    kind="vision",  # 或 language
    profile=profile,
    task="image_score",
    **request_kwargs,
)
```

任务名对照 spec。`content_compliance._complete_json_text` 用 `task="content_gen"`，`kind="language"`；profile 从 `get_language_client()` 取，取不到则 env 回退。

`content_generation_service._build_openai_client` 改为优先 `get_language_client()`，失败再 `.env`。

- [ ] **Step 2: Run related tests**

Run:

```
python -m pytest tests/test_content_compliance.py tests/test_image_score_vl.py tests/test_content_generation_service.py tests/test_token_usage.py -q
```

Expected: PASS。若 mock 没有 `usage`，`parse_completion_usage` 应返回 0，测试仍过。

- [ ] **Step 3: Grep leftover raw creates**

Run: `rg "chat.completions.create" -g "*.py" -g "!web_server_backup.py"`

Expected: 生产路径只剩 `token_usage.complete_chat` 内部一处。测试文件里的 mock 可保留。

---

### Task 4: Usage API

**Files:**
- Modify: `api/routes/model_config_routes.py`
- Test: `tests/test_token_usage_api.py`

**Interfaces:**
- Produces: `GET /api/models/usage?range=today|7d|30d|all`
- Produces: `POST /api/models/usage/clear`
- `by_model[].display_name`：用 `load_models_config()` 里匹配的 `display_name`，匹配不上则用 `model`

- [ ] **Step 1: Write the failing API tests**

```python
# tests/test_token_usage_api.py
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db.engine import init_db
from services.model_config.token_usage import record_token_usage
from src.db.engine import get_session_factory


def _load_router():
    path = Path(__file__).resolve().parents[1] / "api" / "routes" / "model_config_routes.py"
    spec = importlib.util.spec_from_file_location("model_config_routes_isolated", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.router


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "usage_api.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    app = FastAPI()
    app.include_router(_load_router())
    return TestClient(app)


def test_usage_summary_empty(client):
    resp = client.get("/api/models/usage", params={"range": "all"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["totals"]["calls"] == 0


def test_usage_summary_and_clear(client):
    factory = get_session_factory()
    with factory() as session:
        record_token_usage(
            kind="language",
            profile_id="p1",
            provider="deepseek",
            model="deepseek-chat",
            task="content_gen",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            session=session,
        )
        session.commit()
    resp = client.get("/api/models/usage", params={"range": "all"})
    assert resp.json()["totals"]["total_tokens"] == 15
    cleared = client.post("/api/models/usage/clear")
    assert cleared.status_code == 200
    assert client.get("/api/models/usage", params={"range": "all"}).json()["totals"]["calls"] == 0


def test_usage_rejects_bad_range(client):
    resp = client.get("/api/models/usage", params={"range": "yesterday"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_token_usage_api.py -q`

Expected: 404 或 400，因为路由还不存在。

- [ ] **Step 3: Add routes**

```python
@router.get("/usage")
def get_model_usage(range: str = "7d", db: Session = Depends(get_db)):
    from services.model_config.token_usage import query_token_usage
    try:
        summary = query_token_usage(db, range_key=range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "range": range, **summary}


@router.post("/usage/clear")
def clear_model_usage(db: Session = Depends(get_db)):
    from services.model_config.token_usage import clear_token_usage
    deleted = clear_token_usage(db)
    db.commit()
    return {"success": True, "deleted": deleted}
```

`get_db` 与 publishing 路由相同：`session_scope` 或 `Depends` session。若 `model_config_routes` 目前无 DB，按 `api/routes/publishing_routes.py` 的 `get_db` 抄一份。

非法 range：`ValueError` → 400，detail 含 `invalid range`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_token_usage.py tests/test_token_usage_api.py -q`

Expected: PASS

---

### Task 5: Settings tab UI

**Files:**
- Modify: `static/settings.html` — 新 tab + `panel-usage`
- Modify: `static/js/settings_tabs.js` — 切到 usage 时 `loadTokenUsage()`
- Create: `static/js/settings_token_usage.js`
- Modify: `static/css/model_settings.css` — 卡片/表格（复用 `.form-grid` / `.profile-card`）
- Modify: `static/settings.html` 底部 script 引用 `?v=20260824a`

**UI 结构（settings.html 片段）：**

```html
<button type="button" class="settings-tab" data-tab="usage">📈 用量统计</button>

<div id="panel-usage" class="settings-panel" hidden>
  <div class="card">
    <div class="section-head">
      <h2>Token 用量</h2>
      <div class="toolbar-row">
        <select id="usageRangeSelect" class="form-control" style="width:auto;">
          <option value="today">今日</option>
          <option value="7d" selected>近 7 天</option>
          <option value="30d">近 30 天</option>
          <option value="all">全部</option>
        </select>
        <button type="button" class="btn btn-outline btn-sm" id="reloadUsageBtn">刷新</button>
        <button type="button" class="btn btn-outline btn-sm" id="clearUsageBtn">清空统计</button>
      </div>
    </div>
    <p class="section-desc">统计已配置语言模型与视觉模型的接口返回 token，不是账单估算。</p>
    <div id="usageSummaryCards" class="form-grid"></div>
    <h3>按模型</h3>
    <div id="usageByModel"></div>
    <h3>按任务</h3>
    <div id="usageByTask"></div>
    <div id="usageStatusBar" class="status-bar"></div>
  </div>
</div>
```

`settings_token_usage.js`：

- `loadTokenUsage()` → `GET /api/models/usage?range=`
- 卡片：总 token / 语言 / 视觉 / 调用次数（数字用千分位或「1.2万」与发布数据页一致即可，优先千分位）
- 表：HTML table，空态用 spec 文案
- 清空：`confirm('清空本机全部 token 统计？不可恢复。')` 后 `POST /api/models/usage/clear`

- [ ] **Step 1: Implement HTML/JS/CSS**

- [ ] **Step 2: Manual check**

打开 `/settings.html#usage`（hash 也要在 `settings_tabs.js` 支持）。点「测试语言模型」后再刷新用量，应出现 `model_test` 一行。

无法用浏览器工具时：`GET /api/models/usage?range=all` 在测完模型后 `calls >= 1`。

---

### Task 6: Regression + self-check

- [ ] **Step 1: Run focused + related suites**

```
python -m pytest tests/test_token_usage.py tests/test_token_usage_api.py tests/test_content_compliance.py tests/test_image_score_vl.py tests/test_content_generation_service.py tests/test_beijing_time.py -q
```

Expected: PASS

- [ ] **Step 2: Spec coverage check**

- 事件表 + parse/record/query → Task 1
- complete_chat → Task 2
- 全部 create 接入 → Task 3
- API + clear → Task 4
- 设置页 Tab → Task 5
- 非目标（账单/成本/CSV）未做

- [ ] **Step 3: Leftover grep**

`rg "chat.completions.create" -g "*.py"` 仅 wrapper 与测试 mock。
