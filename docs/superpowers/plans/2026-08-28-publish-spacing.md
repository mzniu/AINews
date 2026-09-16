# 自动发布间隔排期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 自动发布按文章间隔入队并写入 `scheduled_at`，支持可配禁发时段、队列改期与顺延，避免多篇 S 级连发。

**Architecture:** 新增 `services/publishing/schedule.py` 统一算档期；`maybe_enqueue_auto_publish_jobs` 入队时写 `scheduled_at`；Worker 按到期时间与禁发窗领取；发布中心配置间隔/禁发并支持改期 API。

**Tech Stack:** Python 3.11, SQLAlchemy, FastAPI, pytest, `zoneinfo` / `src.utils.beijing_time`, 现有 `publish_center.html` + `static/js/shared/datetime.js`。

**Spec:** `docs/superpowers/specs/2026-08-28-publish-spacing-design.md`

## Global Constraints

- 间隔按**文章**（`source_type=ingestion` + `source_id`），同篇各平台共用 `scheduled_at`
- 默认 `interval_minutes: 60`，范围 **15–240**
- 禁发窗按 **Asia/Shanghai**；`scheduled_at` 存 **UTC naive**（与 `datetime.utcnow()` 一致）
- 改间隔不重排队列；取消不顺延；失败重试清空 `scheduled_at`（已知限制）
- 前端改期/展示用 `parseBeijingDatetimeLocal` / `formatBeijingDateTime`（与 `publish_modal.js` 一致）
- 用户未要求则不 git commit
- 不提交 `config/article_scoring.local.yaml`

## File Map

| 文件 | 职责 |
|------|------|
| `services/publishing/schedule.py` | 档期算法、禁发夹紧、改期顺延、配置解析 |
| `services/publishing/auto_publish.py` | 入队时调用 `next_auto_slot` |
| `services/publishing/worker.py` | 禁发窗跳过 ingestion；`scheduled_at` 领取顺序 |
| `services/ingestion/scoring_settings.py` | 读写 `interval_minutes` / `quiet_hours` |
| `config/article_scoring.yaml` | 默认配置 |
| `api/routes/publishing_routes.py` | settings 扩展 + `PATCH .../schedule` |
| `api/schemas/publishing_models.py` | 请求/响应模型 |
| `static/publish_center.html` | 间隔、禁发、定时列、改期 UI |
| `tests/test_publish_spacing.py` | 排期核心 + API + Worker |

---

### Task 1: `schedule.py` 核心算法（P0）

**Files:**
- Create: `services/publishing/schedule.py`
- Test: `tests/test_publish_spacing.py`（前半部分，纯函数）

**Interfaces:**
- Produces: `PublishSpacingConfig` — dataclass `interval_minutes: int`, `quiet_hours_enabled: bool`, `quiet_hours_start: str`, `quiet_hours_end: str`
- Produces: `load_spacing_config(cfg: dict | None = None) -> PublishSpacingConfig`
- Produces: `clamp_quiet_hours(slot_utc_naive: datetime, config: PublishSpacingConfig) -> datetime`
- Produces: `in_quiet_hours(now_utc_naive: datetime, config: PublishSpacingConfig) -> bool`
- Produces: `next_auto_slot(session, *, config: PublishSpacingConfig, now: datetime | None = None) -> datetime`

- [ ] **Step 1: Write failing tests for quiet hours + next slot**

```python
# tests/test_publish_spacing.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.publishing.schedule import (
    PublishSpacingConfig,
    clamp_quiet_hours,
    in_quiet_hours,
    next_auto_slot,
)
from src.db.engine import init_db
from src.db.models.publishing import PublishJob, PublisherAccount


def _cfg(**kwargs) -> PublishSpacingConfig:
    return PublishSpacingConfig(
        interval_minutes=60,
        quiet_hours_enabled=kwargs.get("quiet_hours_enabled", False),
        quiet_hours_start=kwargs.get("quiet_hours_start", "23:00"),
        quiet_hours_end=kwargs.get("quiet_hours_end", "07:00"),
    )


def test_clamp_quiet_cross_midnight_moves_to_next_morning():
    # 2026-08-28 15:30 UTC = 23:30 Beijing → next day 07:00 Beijing = 2026-08-28 23:00 UTC
    slot = datetime(2026, 8, 28, 15, 30, 0)
    out = clamp_quiet_hours(slot, _cfg(quiet_hours_enabled=True))
    assert out == datetime(2026, 8, 28, 23, 0, 0)


def test_clamp_quiet_same_day_window():
    # 12:10 Beijing = 04:10 UTC on same calendar UTC day — use fixed instant:
    # 2026-08-28 04:10 UTC = 12:10 Beijing → clamp to 13:00 Beijing = 05:00 UTC
    slot = datetime(2026, 8, 28, 4, 10, 0)
    cfg = _cfg(quiet_hours_enabled=True, quiet_hours_start="12:00", quiet_hours_end="13:00")
    assert clamp_quiet_hours(slot, cfg) == datetime(2026, 8, 28, 5, 0, 0)


def test_in_quiet_hours_respects_left_closed_right_open():
    cfg = _cfg(quiet_hours_enabled=True)
    inside = datetime(2026, 8, 28, 16, 0, 0)  # 00:00 Beijing next day — adjust: 16 UTC = 00 Beijing same day? 
    # Use beijing_now helper in impl; test via known mapping:
    # 2026-08-28 15:00 UTC = 23:00 Beijing → inside
    assert in_quiet_hours(datetime(2026, 8, 28, 15, 0, 0), cfg) is True
    # 2026-08-28 23:00 UTC = 07:00 Beijing → outside (right-open end)
    assert in_quiet_hours(datetime(2026, 8, 28, 23, 0, 0), cfg) is False


def test_next_auto_slot_empty_queue_returns_now(tmp_path, monkeypatch):
    db_path = tmp_path / "spacing.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    from src.db.engine import get_session_factory

    now = datetime(2026, 8, 28, 10, 0, 0)
    with get_session_factory()() as session:
        slot = next_auto_slot(session, config=_cfg(), now=now)
    assert slot == now


def test_next_auto_slot_respects_pending_article(tmp_path, monkeypatch):
    db_path = tmp_path / "spacing.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    from src.db.engine import get_session_factory

    factory = get_session_factory()
    t0 = datetime(2026, 8, 28, 8, 0, 0)
    with factory() as session:
        acc = PublisherAccount(
            id="a1",
            platform="douyin",
            nickname="n",
            session_path="data/publish/sessions/a1.enc",
            status="active",
        )
        session.add(acc)
        session.add(
            PublishJob(
                account_id="a1",
                video_path="data/videos/a.mp4",
                title="A",
                status="pending",
                source_type="ingestion",
                source_id="art-a",
                scheduled_at=t0,
            )
        )
        session.commit()
        slot = next_auto_slot(session, config=_cfg(interval_minutes=60), now=t0)
    assert slot >= t0 + timedelta(minutes=60)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_publish_spacing.py -q`

Expected: `ModuleNotFoundError` or import errors for `services.publishing.schedule`.

- [ ] **Step 3: Implement `schedule.py`**

要点：

```python
# services/publishing/schedule.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.ingestion.article_scorer import load_scoring_config
from src.db.models.publishing import PublishJob

BJ = ZoneInfo("Asia/Shanghai")
INGESTION = "ingestion"


@dataclass(frozen=True)
class PublishSpacingConfig:
    interval_minutes: int = 60
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "07:00"


def load_spacing_config(cfg: dict | None = None) -> PublishSpacingConfig:
    active = cfg or load_scoring_config()
    auto = (active.get("post_score_automation") or {}).get("auto_publish") or {}
    qh = auto.get("quiet_hours") or {}
    interval = int(auto.get("interval_minutes") or 60)
    interval = min(240, max(15, interval))
    return PublishSpacingConfig(
        interval_minutes=interval,
        quiet_hours_enabled=bool(qh.get("enabled", False)),
        quiet_hours_start=str(qh.get("start") or "23:00"),
        quiet_hours_end=str(qh.get("end") or "07:00"),
    )


def _parse_hhmm(value: str) -> time:
    hour, minute = value.strip().split(":", 1)
    return time(int(hour), int(minute))


def _utc_to_bj(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BJ)


def _bj_wall_to_utc_naive(bj: datetime) -> datetime:
    return bj.astimezone(timezone.utc).replace(tzinfo=None)


def in_quiet_hours(now_utc_naive: datetime, config: PublishSpacingConfig) -> bool:
    if not config.quiet_hours_enabled:
        return False
    start = _parse_hhmm(config.quiet_hours_start)
    end = _parse_hhmm(config.quiet_hours_end)
    if start == end:
        return False
    bj = _utc_to_bj(now_utc_naive)
    t = bj.timetz().replace(tzinfo=None)
    if start < end:
        return start <= t < end
    return t >= start or t < end


def clamp_quiet_hours(slot_utc_naive: datetime, config: PublishSpacingConfig) -> datetime:
    if not config.quiet_hours_enabled:
        return slot_utc_naive
    start = _parse_hhmm(config.quiet_hours_start)
    end = _parse_hhmm(config.quiet_hours_end)
    if start == end:
        return slot_utc_naive
    bj = _utc_to_bj(slot_utc_naive)
    t = bj.timetz().replace(tzinfo=None)
    inside = (start <= t < end) if start < end else (t >= start or t < end)
    if not inside:
        return slot_utc_naive
    end_dt = datetime.combine(bj.date(), end, tzinfo=BJ)
    if start > end and t >= start:
        end_dt = datetime.combine(bj.date() + timedelta(days=1), end, tzinfo=BJ)
    return _bj_wall_to_utc_naive(end_dt)


def _occupied_slots(session: Session) -> list[datetime]:
    rows = (
        session.query(PublishJob.scheduled_at)
        .filter(PublishJob.status.in_(("pending", "uploading")))
        .all()
    )
    now = datetime.utcnow()
    return [row[0] or now for row in rows]


def _last_success_at(session: Session) -> datetime | None:
    row = (
        session.query(func.coalesce(PublishJob.published_at, PublishJob.finished_at))
        .filter(PublishJob.status == "published")
        .order_by(func.coalesce(PublishJob.published_at, PublishJob.finished_at).desc())
        .first()
    )
    return row[0] if row and row[0] else None


def next_auto_slot(
    session: Session,
    *,
    config: PublishSpacingConfig,
    now: datetime | None = None,
) -> datetime:
    now = now or datetime.utcnow()
    interval = timedelta(minutes=config.interval_minutes)
    occupied = _occupied_slots(session)
    last_success = _last_success_at(session)
    anchor = now
    if occupied:
        anchor = max(anchor, max(occupied))
    if last_success:
        anchor = max(anchor, last_success + interval)
    if not occupied and not last_success:
        base = now
    else:
        base = max(now, anchor + interval) if occupied or last_success else now
        if occupied and last_success:
            base = max(now, max(max(occupied), last_success + interval))
        elif occupied:
            base = max(now, max(occupied) + interval)
        elif last_success:
            base = max(now, last_success + interval)

    slot = base
    for _ in range(48):
        slot = clamp_quiet_hours(slot, config)
        need = now
        if occupied:
            need = max(need, max(occupied) + interval)
        if slot < need:
            slot = need
            continue
        return slot
    return slot
```

（实施时把 `next_auto_slot` 的 anchor 逻辑整理成 spec 伪代码，避免重复 `max`；上面为骨架，测试绿为准。）

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_publish_spacing.py -q`

Expected: PASS（Task 1 相关用例）

---

### Task 2: 自动入队写入 `scheduled_at`（P0）

**Files:**
- Modify: `services/publishing/auto_publish.py`
- Modify: `tests/test_publishing_auto_publish.py`
- Test: `tests/test_publish_spacing.py`（入队集成）

**Interfaces:**
- Consumes: `next_auto_slot`, `load_spacing_config` from `schedule.py`
- Produces: `PublishJob.scheduled_at` set on every auto-created job

- [ ] **Step 1: Write failing test**

```python
def test_auto_enqueue_sets_scheduled_at(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.publishing.auto_publish.load_scoring_config",
        lambda: _AUTO_PUBLISH_CFG,
    )
    # ... seed article + video like test_publishing_auto_publish ...
    result = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    jobs = db_session.query(PublishJob).all()
    assert result.get("enqueued")
    assert len(jobs) >= 1
    assert all(j.scheduled_at is not None for j in jobs)
    assert len({j.scheduled_at for j in jobs}) == 1  # same article same slot
```

- [ ] **Step 2: Run test — expect FAIL**（`scheduled_at` 为 None）

- [ ] **Step 3: Patch `maybe_enqueue_auto_publish_jobs`**

在创建 `PublishJob` 前：

```python
from services.publishing.schedule import load_spacing_config, next_auto_slot

spacing = load_spacing_config(config)
existing_slot = (
    session.query(PublishJob.scheduled_at)
    .filter(
        PublishJob.source_type == SOURCE_TYPE,
        PublishJob.source_id == article.id,
        PublishJob.status.in_(("pending", "uploading")),
    )
    .order_by(PublishJob.scheduled_at.asc())
    .first()
)
slot = existing_slot[0] if existing_slot and existing_slot[0] else next_auto_slot(session, config=spacing)
# ...
job = PublishJob(..., scheduled_at=slot)
```

排期异常时 `logger.error` 并 `return {"skipped": True, "reason": "schedule_failed"}`，不建 Job。

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_publishing_auto_publish.py tests/test_publish_spacing.py -q`

Expected: PASS

---

### Task 3: 配置与 Settings API（P0 间隔 / P1 禁发）

**Files:**
- Modify: `config/article_scoring.yaml`
- Modify: `services/ingestion/scoring_settings.py`
- Modify: `api/routes/publishing_routes.py`
- Test: `tests/test_publish_spacing.py`（settings API）

**Interfaces:**
- Produces: `get_auto_publish_settings()` 含 `interval_minutes`, `quiet_hours_*`
- Produces: `save_auto_publish_settings(..., interval_minutes=, quiet_hours_enabled=, ...)`

- [ ] **Step 1: Add YAML defaults**

```yaml
  auto_publish:
    enabled: true
    skip_if_exists: true
    min_grade: S
    interval_minutes: 60
    quiet_hours:
      enabled: false
      start: "23:00"
      end: "07:00"
```

- [ ] **Step 2: Extend `scoring_settings.py`**

- `get_auto_publish_settings` 返回新字段
- `save_auto_publish_settings` 校验 `interval_minutes` 15–240、`HH:MM`、`start != end` when enabled
- 新增 `reshuffle_auto_jobs_in_quiet_window(session)` — **P2**，保存禁发时调用（Task 6）

- [ ] **Step 3: Extend PUT route**

`update_auto_publish_settings_route` 接受 `interval_minutes`, `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`。

- [ ] **Step 4: Tests**

```python
def test_settings_reject_interval_out_of_range(client):
    resp = client.put("/api/publishing/auto-publish/settings", json={"interval_minutes": 5})
    assert resp.status_code == 400
```

Run: `python -m pytest tests/test_publish_spacing.py -k settings -q`

---

### Task 4: `PATCH /jobs/{id}/schedule` + 顺延（P1）

**Files:**
- Modify: `services/publishing/schedule.py` — `reschedule_job_group`, `cascade_auto_jobs`
- Modify: `api/routes/publishing_routes.py`
- Modify: `api/schemas/publishing_models.py`
- Test: `tests/test_publish_spacing.py`

**Interfaces:**
- Produces: `reschedule_publish_job(session, job_id, scheduled_at, *, cascade: bool) -> dict`

- [ ] **Step 1: Schema**

```python
class ReschedulePublishJobRequest(BaseModel):
    scheduled_at: datetime
    cascade: bool = True
```

- [ ] **Step 2: Failing API test**（isolated FastAPI app 或现有 publishing route 测试模式）

- [ ] **Step 3: Implement**

- 解析 `scheduled_at`：与 `create_job` 相同（tz → strip → naive UTC）
- 必须 `> datetime.utcnow()`
- 同 `source_id` pending 任务一起更新
- `cascade=True` 时调用 `cascade_auto_jobs`

- [ ] **Step 4: Run cascade tests**（spec 用例 7–8）

---

### Task 5: Worker 禁发窗 + 领取顺序（P1）

**Files:**
- Modify: `services/publishing/worker.py`
- Test: `tests/test_publish_spacing.py` + extend `tests/test_publishing_scheduled_jobs.py`

**Interfaces:**
- Consumes: `in_quiet_hours`, `load_spacing_config`

- [ ] **Step 1: Test worker skips ingestion in quiet hours**

```python
def test_claim_skips_ingestion_during_quiet_hours(monkeypatch):
    monkeypatch.setattr(
        "services.publishing.worker.load_spacing_config",
        lambda: PublishSpacingConfig(quiet_hours_enabled=True),
    )
    # pending ingestion job due now + manual job due now → claims manual
```

- [ ] **Step 2: Update `_claim_pending_job`**

```python
.order_by(
    func.coalesce(PublishJob.scheduled_at, now).asc(),
    PublishJob.created_at.asc(),
)
# loop candidates: skip if source_type==INGESTION and in_quiet_hours(now, config)
```

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_publishing_scheduled_jobs.py tests/test_publish_spacing.py -k worker -q`

---

### Task 6: 保存禁发窗时重排（P2）

**Files:**
- Modify: `services/publishing/schedule.py` — `reshuffle_jobs_in_quiet_window`
- Modify: `services/ingestion/scoring_settings.py` — `save_auto_publish_settings` 在 quiet 变更时调用
- Test: spec 用例 14

- [ ] **Step 1: Test** — 两篇 pending 落在 23:00–07:00 窗内，保存启用禁发后变为 07:00、08:00

- [ ] **Step 2: Implement** — 按 `source_id` 分组，旧档期升序，从 `clamp_quiet(now)` 起 `next_auto_slot` 链式赋值

- [ ] **Step 3: Run tests**

---

### Task 7: 发布中心 UI（P0 展示 + P1 配置/改期）

**Files:**
- Modify: `static/publish_center.html`

- [ ] **Step 1: 自动发布卡片**

- `#autoPublishInterval` number input 15–240
- `#quietHoursEnabled` checkbox + `#quietHoursStart` / `#quietHoursEnd` type=time
- 加载/保存对接扩展后的 settings API
- 保存间隔成功：`仅影响之后新入队的任务`
- hint 文案（间隔按篇、禁发仅自动、手动可抢发）

- [ ] **Step 2: 队列表格**

- 增加「定时」列；`loadJobs` 里 pending 按 `scheduled_at` 排序
- pending 行「改期」按钮 + 小弹层：`datetime-local` 用 `toBeijingDatetimeLocalValue` / `parseBeijingDatetimeLocal`
- `PATCH /api/publishing/jobs/{id}/schedule` body `{ scheduled_at: iso, cascade: true }`
- **P2：** 同 `source_id` 多行合并显示「本篇 · 档期」

- [ ] **Step 3: 可选摘要**

`#publishQueueSummary`：下一篇 pending 的 `formatBeijingDateTime(scheduled_at)`

- [ ] **Step 4: 手动冒烟**

打开 `/publish_center.html`：改间隔保存、模拟两篇文章入队后队列显示不同定时。

---

### Task 8: 回归与收尾

- [ ] **Step 1: Full test run**

```bash
python -m pytest tests/test_publish_spacing.py tests/test_publishing_auto_publish.py tests/test_publishing_scheduled_jobs.py -q
```

Expected: all PASS

- [ ] **Step 2: Spec coverage self-check**

| Spec 章节 | Task |
|-----------|------|
| 间隔入队 | 1–2 |
| 禁发夹紧 | 1, 5 |
| Settings API | 3 |
| 改期 cascade | 4 |
| Worker | 5 |
| 保存禁发重排 P2 | 6 |
| UI | 7 |
| 已知限制（重试） | 不实现，文档已有 |

- [ ] **Step 3: 更新 spec 状态为「已实施」**（可选，实施完成后）

---

## Spec Coverage Self-Review

- P0/P1/P2 分期与 spec 一致；Task 6 可整任务延后若工期紧。
- 所有 Task 含具体路径与测试命令；`next_auto_slot` 实施时需对照 spec 伪代码整理 anchor 逻辑（Step 3 骨架需 refactor）。
- 时区：API/UI 走 `datetime.js`；禁发用 `ZoneInfo("Asia/Shanghai")`。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-28-publish-spacing.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — 每个 Task 派生子 agent，Task 间做 review  
2. **Inline Execution** — 本会话按 Task 顺序实现，每完成 P0 做一次验收

Which approach?
