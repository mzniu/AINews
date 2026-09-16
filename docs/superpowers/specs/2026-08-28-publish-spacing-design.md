# 自动发布按文章间隔排期

> 日期：2026-08-28  
> 状态：已通过 PM 审核，待实施  
> 范围：出片成功后的自动发布不再扎堆；按文章错开定时；可配禁发时段，落在窗内的自动内容排到开窗之后  
> 已确认：间隔按文章（同一篇各平台共用档期）；默认间隔可配 + 队列改期 + 后续自动任务顺延；禁发时段内自动任务往后排

## 目标

一波抓取里多篇 S 级（或达到自动发布门槛）的文章出片后，**不要马上连着发出**。自动入队时按「上一篇内容 + 间隔」写入定时；若档期落在**禁发时段**内，排到该时段结束之后，并继续保持文章间隔。运营可改间隔和禁发窗，也可改某一篇的时间。改完后，后面还没发出的自动任务按间隔（并再次避开禁发窗）往后顺延。

不在本轮做：按账号日限额、随机抖动、新建独立档期表、出片侧限流、取消后自动把队列往前挤、S 级绕过禁发（V2 再议）。

## 成功指标（上线后如何算做对）

| 指标 | 说明 |
|------|------|
| **主指标** | 同一自然日内，相邻两篇**自动发布**的首条平台任务，墙上时钟间隔 ≥ 配置的 `interval_minutes`（允许 Worker 执行耗时带来的几分钟偏差）。 |
| **辅指标** | 禁发窗启用时，窗内实际发出的 `source_type=ingestion` 任务数 ≈ 0。 |
| **体验指标** | 发布中心能看清每篇「计划几点发」；改间隔 / 改期后队列行为与文案说明一致。 |

本轮可不埋点，但日志应记录 `auto_publish` 入队时的 `article_id`、`scheduled_at`、`interval_minutes`。

## 用户可见说明（发布中心文案要点）

运营需在 UI 或 hint 中看到以下说明（不必一字不差，语义须保留）：

1. **间隔按「内容篇」计算**：同一篇会连续发到各已登录平台；下一篇与上一篇的**开始时间**至少相隔 N 分钟（不是等各平台都发完再隔 N 分钟）。
2. **禁发仅限制自动发布**：该时段内出片的自动任务会排到开禁之后；**手动发布**不受禁发窗限制（突发要闻可用手动发布立即发出）。
3. **修改间隔不重排队列**：保存新间隔只影响**之后新入队**的任务；已在队列里的档期不变（保存时 toast 提示）。
4. **失败重试可能连发**：重试会清空定时并尽快发出；多条重试任务在开禁后可能连续执行（见「已知限制」）。

可选增强（P1 UI）：队列摘要「当前 N 篇待发，下一篇约 HH:MM（北京时间）」。

## 实施分期（PM）

| 阶段 | 能力 |
|------|------|
| **P0** | `next_auto_slot` + 自动入队写 `scheduled_at`；发布间隔配置；队列展示定时、pending 按档期排序；Worker 按 `scheduled_at` 领取顺序 |
| **P1** | 禁发窗（入队夹紧 + Worker 不领自动任务）；`PATCH` 改期 + cascade；发布中心间隔/禁发/改期 UI |
| **P2** | 保存禁发设置时重排落在窗内的 pending 自动任务；队列按 `source_id` 分组展示 |

P0 应先可独立验收，再叠 P1。

## 背景

现有链路已经有发布队列，缺的是自动路径的排期：

1. 出片成功 → `maybe_enqueue_auto_publish_jobs` 给每个已登录平台建一条 `PublishJob(status=pending)`，**不写 `scheduled_at`**。
2. `PublishWorker` 每 5 秒领取「已到期」任务：`scheduled_at` 为空或 ≤ 现在；全局串行，一次只发一条。
3. 手动 `POST /api/publishing/jobs` 已支持 `scheduled_at`；发布中心表格对 pending 会显示「定时 …」。
4. 自动发布设置只有开关和最低等级，写在 `config/article_scoring.yaml` / `article_scoring.local.yaml`。

Worker 串行只能避免两个浏览器同时跑，**不能**把多篇文章在墙上时钟上错开一小时，也不能避开夜间。媒体流水线一篇接一篇出片时，前一篇可能已经 `published`、队列已空，下一篇仍会立刻入队并立刻被领取。

## 方案对比

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A. 入队时写 `scheduled_at`（采用）** | 按文章算一个档期，同一篇所有平台任务共用；禁发窗在算档期时夹紧；Worker 原到期逻辑 + 窗内不领自动任务 | 队列看得见几点发；改期自然；复用已有字段 | 改期/顺延/跨午夜窗要写清楚 |
| B. Worker 临发再卡间隔 | 任务仍立刻 pending，领取时再跳过 | 改动面小 | 队列上看不出未来时间；无法改某一篇 |
| C. 新建档期表 | 文章一层、任务一层 | 模型更干净 | 与现有 Job/Worker/手动定时重复，本轮过重 |

采用 **A**。

## 核心概念

**档期（slot）**：一篇「内容」计划开始发布的 **UTC naive** 时间（与现网 `datetime.utcnow` / 手动定时入库一致），写入该内容下所有相关 `PublishJob.scheduled_at`。

- 自动发布：`source_type = "ingestion"` 且 `source_id = article.id` 的一组 pending/uploading 任务共用一个档期。
- 无 `source_id` 的手动任务：每个 Job 自己是一个档期。
- 同一篇文章的抖音 / 视频号等仍按现有 Worker **串行**，一篇内各平台不必再隔一小时。

**间隔（interval）**：相邻两篇内容档期的最小差值。默认 **60 分钟**，允许 **15～240**。

**禁发时段（quiet hours）**：按**北京时间**的每日窗口。档期落在窗内的**自动**任务改到窗结束时刻，再按间隔排开。默认关闭；预设窗口 `23:00`–`07:00`（跨午夜）。

**上一篇锚点**：计算新档期时，取下面更晚的那个：

1. 队列占用：`pending` / `uploading` 任务的档期（`scheduled_at`；若为空则视为「现在」）。
2. 最近一次**成功发布**：任意平台 `status=published` 的 `published_at`（若空则用 `finished_at`）。

`failed` / `cancelled` 不占锚点。已发出的只通过「最近成功发布时间」影响新任务。

## 时区约定

| 场景 | 规则 |
|------|------|
| 数据库存储 | `scheduled_at` 等为 **UTC naive**（与 `datetime.utcnow()`、现有手动定时一致）。 |
| 禁发窗判断 | 一律按 **Asia/Shanghai** 墙钟。 |
| API 入参 | 前端用 `parseBeijingDatetimeLocal` + `toISOString()`（与 `publish_modal.js` 相同）；服务端对带 tz 的 datetime **去 tz 后当 UTC naive 存**（与 `POST /jobs` 一致）。 |
| UI 展示 | 一律 `formatBeijingDateTime`（北京时间）。 |

禁止在改期 UI 直接填 naive 字符串而不经 `datetime.js` 转换。

## 排期算法

先算间隔，再避开禁发窗，若夹紧后撞上已有档期则继续 `+ interval`（并再次检查禁发窗）。伪代码：

```
base = max(now, max(occupied ∪ {last_success}) + interval)
       若无占用且无成功记录 → now

slot = base
loop:
    slot = clamp_quiet(slot)          # 落在禁发窗内则改到本轮窗口的结束时刻
    need = max(now, max(occupied) + interval)  # 无占用时为 now
    if slot < need:
        slot = need
        continue
    return slot
```

`clamp_quiet`（北京时间）：

- 未启用、或缺起止、或 `start == end` → 原样返回。
- `start < end`：当天同一段（如 12:00–13:00）。时刻 ∈ [start, end) 则改到**当天 end**。
- `start > end`：跨午夜（如 23:00–07:00）。时刻 ≥ start 则改到**次日 end**；时刻 < end 则改到**当天 end**。
- 窗口为左闭右开：`07:00` 整点已开禁，可以发。

自动入队时：

1. 门槛、story gate、合规、`skip_if_exists` 与现在一致。
2. `slot = next_auto_slot(...)`（含禁发夹紧）。
3. 本篇文章新建的每条 Job 都写同一个 `scheduled_at = slot`（不再留空）。
4. 同一篇文章若因 `skip_if_exists` 只补尚未入队的平台：沿用该文章已有 pending/uploading 任务的档期，**不再** `+interval`，也**不再**因补平台而改档期。

手动 `POST /jobs`：调用方传入的 `scheduled_at` 照旧，**不**套间隔、**不**套禁发窗（人工指定时间）。该任务一旦 pending/uploading/published，会成为后续**自动入队**的锚点。

## 禁发窗与 Worker

- Worker 在北京时间处于禁发窗内时，**不领取** `source_type=ingestion` 的任务（即使 `scheduled_at` 已到期或为空）。手动任务照常领取。
- 领取顺序：到期 pending 按 **`scheduled_at` 升序**（`NULL` 视为最早），再 `created_at` 升序（修正现网仅按 `created_at` 可能乱序的问题）。
- 窗结束后按已写入的档期领取：入队时已按间隔排开（07:00、08:00…），不会在开禁瞬间连发。
- 重试：现有 `POST .../retry` 仍把失败任务打回 `pending` 并清空 `scheduled_at`。若当前在禁发窗内，Worker 不会领；开禁后该任务视为「立刻到期」。若同时有多条空档期自动任务，开禁后会按 Worker 串行连发（重试是人工介入，本轮不自动再拆间隔）。想夜间立刻发，用手动创建任务。

保存禁发设置时（**P2**）：把档期落在**新窗口内**的 pending 自动任务，按当前间隔从 `clamp_quiet(now)` 起重排（与新入队同一套 `next_auto_slot` 逻辑，按原档期升序逐篇赋值）。窗外的 pending 不动。改间隔本身仍不重排整队。

## 改期与顺延

新接口：`PATCH /api/publishing/jobs/{job_id}/schedule`

```json
{ "scheduled_at": "2026-08-28T13:30:00.000Z", "cascade": true }
```

（前端由北京时间 `datetime-local` 经 `parseBeijingDatetimeLocal` → `toISOString()` 生成。）

规则：

- 仅 `pending` 可改期。`uploading` / `published` / `failed` / `cancelled` 返回 400。
- `scheduled_at` 必须晚于当前 UTC 时间。
- 人工改期 **允许**落到禁发窗内（队列上显示北京时间）；Worker 窗内仍不领自动任务。前端提示：「落在禁发时段内的自动任务不会在该时段发出」。
- 若该 Job 有 `source_type` + `source_id`：同一组里所有 **pending** 任务一起改到新档期。
- `cascade` 默认 `true`：
  - 其他 `pending` 且 `source_type=ingestion` 的文章组，当前档期晚于（含等于）被改那组的**旧**档期。
  - 按旧档期升序，从 `next_auto_slot(从 new_slot 起算)` 依次赋值（每步都夹紧禁发窗）。
  - 手动任务不参与顺延。
- `cascade=false`：只改这一组。
- 改默认间隔 **不会**重写已在队列里的档期。

取消某一条或某一篇：**不**自动把后面的任务往前抽。

## 配置

`config/article_scoring.yaml` 的 `post_score_automation.auto_publish`：

```yaml
auto_publish:
  enabled: true
  skip_if_exists: true
  min_grade: S
  interval_minutes: 60
  quiet_hours:
    enabled: false
    start: "23:00"   # 北京时间 HH:MM
    end: "07:00"
```

运行时覆盖仍写 `config/article_scoring.local.yaml`（不提交 Git）。

> **技术债（非阻塞）：** 发布节奏配置挂在 `article_scoring.yaml` 语义略别扭；后续可迁到 `config/publishing_spacing.yaml`，本轮不迁。

`GET/PUT /api/publishing/auto-publish/settings` 增加：

- `interval_minutes`
- `quiet_hours_enabled`
- `quiet_hours_start`
- `quiet_hours_end`

PUT 可只改其中一部分。校验：

- `interval_minutes` 非整数或越出 15–240 → 400。
- 时刻必须是 `HH:MM`（24 小时）。`start == end` 且 `quiet_hours_enabled=true` → 400（禁止 24 小时全禁，避免任务永远发不出去）。

## API

| 方法 | 路径 | 作用 |
|------|------|------|
| GET/PUT | `/api/publishing/auto-publish/settings` | 间隔 + 禁发窗 |
| PATCH | `/api/publishing/jobs/{job_id}/schedule` | 改期；可选顺延 |
| GET | `/api/publishing/jobs` | 已有 `scheduled_at`；无需改形状 |

`PATCH` 响应：`{ success, job_id, scheduled_at, updated_job_ids, cascaded_job_ids }`。

列表 API 仍 `created_at desc`。发布中心前端：**pending** 按 `scheduled_at` 升序（空视为现在）排前，其余按创建时间；**P2** 可按 `source_id` 合并展示「本篇 N 个平台 · 档期 HH:MM」。

## UI（发布中心）

自动发布卡片增加：

- **发布间隔（分钟）**，默认 60，范围 15–240。保存成功提示：「仅影响之后新入队的任务。」
- **禁发时段**：开关 + 开始时间 + 结束时间（北京时间）。说明：跨午夜时开始晚于结束（如 23:00–07:00）；推荐夜间运营开启，默认关闭。
- 原有开关、最低等级、用户可见说明（见上文）。

发布队列表格：

- 「定时」列，北京时间（`formatBeijingDateTime`）。
- pending 「改期」：`datetime-local`（北京时间）+ 「顺延后面的自动任务」（默认勾选）。
- 可选摘要行：下一篇待发时间。
- 现有取消 / 重试保留。

不新增独立页面。

## 数据流

```
出片成功
    → maybe_enqueue_auto_publish_jobs
    → next_auto_slot(间隔, 锚点, 禁发窗)
    → PublishJob.scheduled_at = slot
    → Worker：到期 且（手动 或 不在禁发窗）才领取 ingestion 自动任务
    → 成功后 published_at 成为新锚点

夜间入队（窗已启用）
    → 档期夹到开禁时刻（如 07:00），后续文章 08:00、09:00…

用户改期 / 保存禁发窗（P2 重排）
    → 改期可 cascade；保存新窗口时重排落在窗内的 pending 自动任务
```

## 已知限制（V1 接受，V1.1 可改进）

| 限制 | 说明 |
|------|------|
| 重试连发 | 多条失败重试在开禁后可能连续发出，不重新套用间隔。 |
| 改间隔不重排 | 已在队列的任务保持原档期。 |
| 突发要闻 | 自动路径受禁发窗约束；需用手动发布抢时效。 |
| 一篇多平台耗时 | 间隔从「本篇开始发」算起，末平台与下一篇首平台间隔可能短于 N 分钟。 |

## 错误与边界

| 情况 | 行为 |
|------|------|
| 间隔配置损坏 / 缺省 | 按 60 分钟 |
| 禁发未启用或缺时刻 | 不夹紧 |
| 改期到过去 | 400 |
| 改非 pending | 400 |
| 排期计算失败 | 不建 Job，打 error；不抛给媒体流水线 |
| 同一篇补平台 | 用已有档期 |
| 手动任务 | 不套间隔/禁发；可成为自动入队锚点；Worker 窗内仍可领取手动任务 |
| 开禁瞬间 | 依赖入队时已错开的 `scheduled_at`，不在 07:00 把窗内积压一次性打出 |
| 时区 | 见「时区约定」 |

## 测试

新文件 `tests/test_publish_spacing.py`：

1. 空队列、无成功记录 → 档期 ≈ now。
2. pending 文章 A 档期 T → 新文章 B ≥ T + interval。
3. A 已 published 且队列空、距今不足 interval → B 等到 `published_at + interval`。
4. 距上次成功已超过 interval → B 立刻。
5. 同文章两个平台 `scheduled_at` 相同。
6. `skip_if_exists` 补平台沿用已有档期。
7. 改期 + cascade；`cascade=false` 时后面不变。
8. 手动 pending 不进 `cascaded_job_ids`，但抬高自动入队锚点。
9. `interval_minutes` 越界 PUT → 400。
10. 禁发 23:00–07:00：23:30 入队 → 档期为次日 07:00；紧接着第二篇 → 08:00。
11. 禁发 12:00–13:00：12:10 入队 → 当天 13:00。
12. `start == end` 且启用 → 400。
13. Worker：窗内不领取 ingestion 任务；窗内可领取手动任务；按 `scheduled_at` 顺序领取。
14. 保存新禁发窗后，落在窗内的 pending 自动任务被重排到开禁后且保持间隔（P2）。
15. 现有自动发布门槛测试仍绿；Worker 仍不领取未来 `scheduled_at`。

## 文件地图（实施时）

- 新增：`services/publishing/schedule.py` — `next_auto_slot`、`clamp_quiet`、`in_quiet_hours`、文章组、改期+顺延、保存窗口后重排。
- 修改：`services/publishing/auto_publish.py` — 入队时写 `scheduled_at`。
- 修改：`services/publishing/worker.py` — 禁发窗内跳过 ingestion 任务；领取排序。
- 修改：`services/ingestion/scoring_settings.py` — 读写间隔与禁发窗。
- 修改：`config/article_scoring.yaml`、`api/routes/publishing_routes.py`、`api/schemas/publishing_models.py`。
- 修改：`static/publish_center.html` — 间隔、禁发窗、定时列、改期。
- 测试：`tests/test_publish_spacing.py`；必要时补 `test_publishing_auto_publish.py`、`test_publishing_scheduled_jobs.py`。

不修改媒体流水线触发（夜间仍可出片，只是发布往后排）。

## 非目标

- 按账号 / 按平台再套一层一小时。
- 随机抖动、每日上限。
- 取消或失败后自动把队列往前挤。
- 改间隔时重排整个队列（改禁发窗 P2 只重排落在新窗口内的自动 pending）。
- 独立「档期」ORM 表。
- 禁发窗内禁止手动发布。
- S 级 / 突发绕过禁发（V2）。

## PM 审核记录

- **结论：** 有条件通过 → 已合并必改项（成功指标、用户说明、时区约定、实施分期、已知限制）。
- **审核日期：** 2026-08-28
