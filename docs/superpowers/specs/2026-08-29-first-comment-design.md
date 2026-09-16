# 发布后自动首评（First Comment）

> 日期：2026-08-29  
> 状态：**有条件通过（首席架构师审阅）— P0 已于 2026-08-29 实现**  
> 范围：视频发布成功后，由作者账号自动在作品下发布一条首评；评论文案在生成标题/摘要时一并产出  
> 已确认：首评与发布解耦状态；生成时产出 `first_comment`；**P0 仅抖音**；**发布重试时若首评已 `posted` 则跳过**；**总开关在发布中心**

## 目标

短视频发布成功后，**自动以作者身份发一条首评**，用于：

1. **引导互动**：承接口播稿末尾「可回答的争议 / 评论开口」，把观众从「看完」推到「留言」。
2. **补充信息**：正文/描述放不下的轻补充（P0 禁止外链；P2 可议是否允许站内话题引用）。
3. **改善互动信号**：平台推荐模型会预估点赞、评论、评论区停留等；空评论区会拖累后续曝光（见 `docs/research/2026-08-19-short-video-growth-research.md`）。

**不在本轮做**：自动回复观众评论、多轮评论机器人、置顶评论（各平台能力差异大）、按 A/B 自动选文案（P3 可选）。

## 成功指标（上线后如何算做对）

| 指标 | 说明 |
|------|------|
| **主指标** | 启用首评的平台，`comment_status=posted` 占比 ≥ 80%（排除 `unsupported` / 用户主动关闭）。 |
| **辅指标** | 有首评作品 vs 无首评作品，7 日内 `comment_count` 中位数提升（需 metrics 回流对比，P1 起可观测）。 |
| **体验指标** | 资讯库/出片预览可看到并编辑 `first_comment`；发布队列可看到首评状态，失败可重试。 |

日志应记录：`job_id`、`platform`、`platform_post_id`、`first_comment` 长度、`comment_status`、失败原因（截断）。

## 用户可见说明（文案要点）

运营需在 UI 或 hint 中看到（语义须保留）：

1. **首评由作者账号发出**：与视频同一账号，显示在评论区，不是私信。
2. **文案在出片时生成**：与标题、口播同一轮 LLM 产出，可在资讯库或发布前修改。
3. **发评失败不影响「已发布」**：视频已发出则任务仍为 `published`；首评单独显示失败并可重试。
4. **部分平台有延迟**：作品入库后才会出现评论框，系统会等待若干秒再发（默认 15s，可配）。
5. **评论可能进审核**：提交成功 ≠ 观众立即可见；以平台后台为准。

## 实施分期（PM）

| 阶段 | 能力 |
|------|------|
| **P0** | 内容生成 `first_comment`；`video_draft_json` 存储；`PublishJob` 快照字段；**仅抖音** `post_first_comment`（与发布**同一次**浏览器会话）；`comment_status` 落库；**发布中心**总开关 |
| **P1** | 发评失败重试 API + 发布队列/发布中心状态展示；资讯库预览编辑首评 |
| **P2** | 快手、视频号、小红书；按平台 `comment_delay_sec` 异步发评（若单条耗时过长） |
| **P3** | 按平台子开关；指标对比看板；prompt A/B（可选） |

P0 应先通过 **抖音首评 Spike**（见审阅 §0），再写码。

## 背景

### 现有链路

```
ingestion 出片
  → content_generation_service.generate_video_content()
  → video_draft_json（main_line1, summary, tags, voiceover_script…）
  → media_pipeline 成片
  → maybe_enqueue_auto_publish_jobs
  → PublishJob（title, description, tags, scheduled_at…）
  → PublishWorker → adapter.publish_video()
  → job.status = published, platform_post_id / url
  → 结束（无 post-publish hook）
```

### 缺口

| 已有 | 缺失 |
|------|------|
| 口播 prompt 要求「结尾留可回答的争议」 | 无独立 `first_comment` 字段 |
| `metadata_bridge` 映射 title/description/tags | 无 comment 透传 |
| 四平台 `publish_video` 浏览器自动化 | 无 `post_first_comment` |
| metrics 只读 `comment_count` | 无写评论路径 |
| `PlatformAdapter` / `PublishPayload` | 无评论相关类型 |

### 产品动机（调研摘要）

抖音等平台公开表述推荐会预估**评论区停留、互动**等行为。本库历史样本中评论中位数偏低（见增长调研文档）。首评是低成本试探：用作者自问一句降低观众开口门槛。

## 方案对比

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A. 发布成功后同会话发评（采用为 P0 默认）** | `publish_video` 成功后 adapter 继续操作评论框 | 实现简单；复用登录态 | 作品入库延迟时需轮询；发布耗时变长 |
| B. 独立 comment job 队列 | `PublishJob` 发布后 enqueue `CommentJob` | 发布与发评解耦；易重试 | 多一张表或状态机；worker 复杂度上升 |
| C. 平台 Open API 发评 | 调官方接口 | 稳定 | 各平台创作者 API 不统一 / 不可用 |
| D. 仅生成文案，人工粘贴 | UI 展示复制按钮 | 零风控 | 无法「立刻」自动 |

采用 **A 为 P0**；发评失败与重试逻辑按 **B 的状态字段**建模（不新建表），P2 若单条发评超过 60s 可拆异步 worker 步骤。

> **架构修正（审阅）：** 现网 `DouyinAdapter.publish_video` 在 `with open_adapter_browser(...)` 返回时**已关闭浏览器**，不能在 orchestrator 里「先 `publish_video` 再 `post_first_comment`」。P0 须在**同一次** `open_adapter_browser` 上下文内完成发布 + 首评（见 § 发布流程）。

## 核心概念

**首评（first comment）**：视频发布成功后，由**同一创作者账号**在该作品下发布的**第一条作者评论**。本轮不区分「置顶评论」与「普通评论」，统一称首评。

**文案来源**：

1. **生成时**：`content_generation_service` LLM JSON 新增 `first_comment`。
2. **存储**：`IngestedArticle.video_draft_json.first_comment`。
3. **入队快照**：`PublishJob.first_comment_text`（与 `title` 同理，避免 draft 后改影响已排队任务）。

**发评时机**：

- `comment_delay_sec`（默认 **15**）：发布后等待，轮询作品是否出现在创作者后台列表。
- 最长等待 `comment_wait_max_sec`（默认 **60**）：超时则 `comment_status=failed`，可重试。

**状态独立**：`job.status=published` 与 `comment_status` 分离。发评失败**不**把发布改回 `failed`。

## 内容生成

### 新增字段 `first_comment`

| 属性 | 规则 |
|------|------|
| 长度 | **15～50 汉字**（生成按最严平台上限；各平台 `max_comment_length` 可更短） |
| 风格 | 口语、可回复；优先**问句**或轻观点；承接口播结尾争议 |
| 禁止 | emoji；外链；「点赞关注」「评论区见」空泛引导；与正文矛盾 |
| 与口播关系 | 允许改写 `voiceover_script` 末句，**不得完全复制**超过 20 字 |

### Prompt 接入（`config/content_prompts.yaml`）

新增 `first_comment_patterns`（可在设置页覆盖，写入 `content_prompts.local.yaml`）：

```yaml
first_comment_patterns: |
  【首评 first_comment】
  - 视频发布成功后由作者账号自动发到评论区
  - 15~50字，必须是观众愿意回复的一句（问句优先）
  - 承接口播稿结尾「可回答的争议」，但不要与 voiceover_script 末句雷同
  - 禁止 emoji、链接、点赞关注、标题党
```

`content_generation_service` 的 JSON schema / compliance 增加 `first_comment` 校验（长度、违禁词复用 `validate_publish_payload` 同类词表）。

### 透传

```
video_draft_json.first_comment
  → metadata_bridge.PublishDraftMetadata.first_comment
  → auto_publish / POST /jobs → PublishJob.first_comment_text
```

手动快速发布：若关联了 ingestion 源，预填 draft 中的 `first_comment`；可留空（`comment_status=none`）。

## 数据模型

### `PublishJob` 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `first_comment_text` | TEXT, nullable | 入队时快照；空表示不发评 |
| `comment_status` | VARCHAR(16) | 见下表 |
| `comment_posted_at` | DateTime, nullable | 发评成功时间（UTC naive） |
| `comment_error_message` | TEXT, nullable | 最后一次失败原因 |
| `comment_retry_count` | Integer, default 0 | 发评重试次数 |

**`comment_status` 枚举**

| 值 | 含义 |
|----|------|
| `none` | 无首评文案或未启用 |
| `pending` | 发布成功，等待/正在发评 |
| `posted` | 发评提交成功（不保证已过审展示） |
| `failed` | 发评失败，可重试 |
| `skipped` | 平台不支持或用户关闭 |
| `unsupported` | 平台 capability 未开启 |

现有 `POST .../retry`（发布重试）：

- **若 `comment_status == posted`：不再发首评**（PM 已确认，无需二次确认弹窗）。
- 若 `comment_status in (failed, pending, none)` 且仍有 `first_comment_text`、总开关开启、平台支持：发布重试成功后可再次尝试发评（仅当上次发布未成功或首评未成功时）。

入队时**不清空** `first_comment_text`；发布重试**不清空** `comment_status=posted`。

### 平台能力（`config/publishing_platforms.yaml`）

```yaml
capabilities:
  account_login: true
  video_publish: true
  first_comment: false   # 按平台逐步 true

limits:
  max_comment_length: 100
  comment_delay_sec: 15
  comment_wait_max_sec: 60
```

`platform_capabilities.py` 新增 `can_post_first_comment(platform_id) -> bool`。

## 发布流程

### 适配器接口（`adapters/base.py`）

```python
@dataclass
class CommentResult:
    success: bool
    comment_id: str | None = None
    error_message: str | None = None

@dataclass
class PublishPayload:
    # ... 现有字段 ...
    first_comment: str | None = None   # 可选；非空且开关开启时在同会话内发评

class PlatformAdapter(ABC):
    def post_first_comment(
        self,
        session_path: Path,
        *,
        post_id: str | None,
        post_url: str | None,
        title: str | None,
        text: str,
        delay_sec: int = 15,
        wait_max_sec: int = 60,
    ) -> CommentResult:
        """独立会话发评（P1 retry-comment 用）。"""
        return CommentResult(success=False, error_message="unsupported")
```

`title` 用于作品列表模糊匹配（`platform_post_id` 不可靠时的兜底）。

### P0 抖音：同会话发布 + 首评（审阅强制）

在 `DouyinAdapter.publish_video` **内部**，保持现有 `with open_adapter_browser(...)` 块，在 `click_douyin_publish` 成功后：

```
if payload.first_comment and settings.first_comment_enabled and can_post_first_comment("douyin"):
    comment_result = post_douyin_first_comment(page, ...)   # douyin_form.py
else:
    comment_result = skipped
return PublishResult(success=True, ..., comment_result=comment_result)  # 或并列字段
```

**禁止**在 orchestrator 中先关闭浏览器再调 `post_first_comment`。

`PublishResult` 可扩展可选字段 `comment_result: CommentResult | None`，或由 orchestrator 从 adapter 返回值一并读取。

### Orchestrator 改造（`orchestrator.py`）

```
payload = PublishPayload(..., first_comment=job.first_comment_text if should_post_comment(job) else None)
result = adapter.publish_video(session_file, payload)

if result.success:
    job.status = published
    # 从 result.comment_result 或 adapter 侧已完成的逻辑写入 comment_status
```

`should_post_comment(job)`：`first_comment_text` 非空 + 发布中心总开关开启 + 平台 `first_comment` capability + **`comment_status != posted`**（发布重试时跳过已发首评）。

发评失败：`job.status` 仍为 `published`；`comment_status=failed`。

### 发评重试（P1）

`POST /api/publishing/jobs/{job_id}/retry-comment`（P1）

- 前置：`job.status=published`，`comment_status in (failed, pending)`，`first_comment_text` 非空，`comment_status != posted`。
- 行为：新开浏览器会话，调用 `adapter.post_first_comment(...)`；`comment_retry_count += 1`。
- 上限：默认 3 次，可配。

`POST .../retry`（发布重试）：**若 `comment_status == posted` 一律不再发首评**（PM 已确认）。

## 各平台实现要点

| 平台 | P 阶段 | 实现思路 | 主要风险 |
|------|--------|----------|----------|
| **抖音** | P0 | 发布成功 → 创作者中心「内容管理」→ 匹配标题/时间 → 详情页评论框 → 拟人输入发送 | 入库延迟；选择器变更 |
| **快手** | P1 | 同上模式 | 同左 |
| **微信视频号** | P2 | 助手后台作品列表 → 详情评论 | 评论审核；DOM 差异大 |
| **小红书** | P2 | 笔记详情评论 | 风控更严；字数限制 |

### 通用自动化步骤（`*_form.py`）

1. `sleep(delay_sec)` 后进入作品列表页。
2. 轮询（每 5s，最多 `wait_max_sec`）：按 `platform_post_id` 或标题匹配最新作品。
3. 打开详情，定位评论输入框（selector 写入 `docs/publishing/{platform}_selectors.md`）。
4. `human_type` + 点击发送。
5. 校验：toast 成功 / 评论列表出现正文前缀。

失败分类写入 `comment_error_message`：`work_not_found` / `selector_miss` / `submit_rejected` / `timeout`。

## 配置

### 全局开关（`config/publishing_platforms.yaml` → `defaults.post_publish`）

```yaml
defaults:
  post_publish:
    first_comment:
      enabled: true              # 默认开启；运营在发布中心关闭
      retry_max: 3
```

运行时覆盖：`config/publishing_platforms.local.yaml`（不提交 Git），与自动发布 local 覆盖模式一致。

### 发布中心 UI（P0 必做，PM 已确认）

自动发布卡片下方或独立「发布后首评」区块：

- **启用自动首评** checkbox（对应 `first_comment.enabled`）
- hint：仅抖音生效（P0）；关闭后新任务仍生成文案但不自动发送；已 `posted` 的不会重复发送
- `GET/PUT /api/publishing/post-publish/settings`（或并入现有发布相关 settings 路由）

**不在系统配置 / settings.html 放总开关**（P0）。`first_comment_patterns` 仍走 `content_prompts` 设置 Tab（P1）。

## API

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/api/publishing/jobs` | 响应增加 `first_comment_text`, `comment_status`, `comment_posted_at`（可选隐藏 error） |
| POST | `/api/publishing/jobs` | 可选 body `first_comment_text`；默认从 draft 预填 |
| POST | `/api/publishing/jobs/{id}/retry-comment` | P1：重试发评 |
| GET/PUT | `/api/publishing/post-publish/settings` | P1：总开关等（可选，初版可只 YAML） |

`PublishJobResponse` 扩展字段；列表不返回 `comment_error_message` 详情时可单独 `GET /jobs/{id}` 查看。

## UI

| 位置 | 内容 |
|------|------|
| **发布中心** | P0 总开关；队列区首评状态；快速发布可选填首评 |
| **发布队列** `/publish-queue` | P1 列「首评」+ 重试 |
| **系统配置** | P1 仅 `first_comment_patterns` 编辑，不放总开关 |

## 数据流

```
generate_video_content
  → first_comment 写入 video_draft_json

出片 / 入队
  → PublishJob.first_comment_text = snapshot
  → comment_status = none（发布前）

publish_video 成功
  → comment_status = pending
  → post_first_comment（同会话）
  → posted | failed

metrics 次日同步
  → comment_count 回流（只读，验证效果）
```

## 合规与安全

- `first_comment` 走与 `title`/`description` 相同的违禁词校验。
- 频率：复用 `human_pacing`；单账号连续发评间隔 ≥ 发布间隔（不额外加规则，靠发布串行）。
- 日志不打印完整评论正文到 info（可 debug 级或截断）。

## 已知限制（V1 接受）

| 限制 | 说明 |
|------|------|
| 审核不可见 | `posted` 仅表示提交成功 |
| 重复发评 | 发布重试时 `comment_status=posted` **强制跳过**（PM 已确认） |
| 选择器脆弱 | 平台改版需更新 `*_form.py` |
| 无 API | 全靠浏览器自动化，与发布相同运维成本 |
| 视频号/小红书 P2 | P0 仅抖音 |

## 错误与边界

| 情况 | 行为 |
|------|------|
| `first_comment` 为空 | `comment_status=none`，不发评 |
| 平台 `first_comment: false` | `comment_status=unsupported` |
| 发布失败 | 不尝试发评 |
| 作品 60s 内找不到 | `failed`，`work_not_found` |
| 评论框 DOM 变化 | `failed`，`selector_miss` |
| 文本超长 | 入队前截断或 400（按平台 `max_comment_length`） |
| 总开关关闭 | 入队时 `first_comment_text` 仍可有值但不发，`skipped` |

## 测试

新文件 `tests/test_first_comment.py`：

1. `generate_video_content` 返回含 `first_comment`（mock LLM）。
2. compliance 拒绝违禁首评。
3. `metadata_bridge` / `auto_publish` 快照到 `PublishJob.first_comment_text`。
4. orchestrator：发布成功 + 有文案 → 调用 `post_first_comment`；失败 → `published` + `comment_failed`。
5. orchestrator：无文案 → `comment_status=none`。
6. `retry-comment`：仅 `published` + `failed` 可调用。
7. 抖音 adapter（集成 / 录屏 fixture）：mock 页面发评成功路径。

现有 `test_publishing_auto_publish.py` 补断言：入队字段含 `first_comment_text`（当 draft 有时）。

## 文件地图（实施时）

| 文件 | 职责 |
|------|------|
| `config/content_prompts.yaml` | `first_comment_patterns` |
| `services/content_generation_service.py` | 生成 + 校验 `first_comment` |
| `services/publishing/metadata_bridge.py` | `PublishDraftMetadata.first_comment` |
| `services/publishing/auto_publish.py` | 写入 `first_comment_text` |
| `api/routes/publishing_routes.py` | 响应字段、`retry-comment` |
| `api/schemas/publishing_models.py` | Pydantic 扩展 |
| `services/publishing/orchestrator.py` | 发布后调 `post_first_comment` |
| `services/publishing/adapters/base.py` | `CommentResult`、`post_first_comment` |
| `services/publishing/adapters/douyin_form.py` | P0 抖音发评 |
| `config/publishing_platforms.yaml` | `capabilities.first_comment`、`limits` |
| `services/publishing/platform_capabilities.py` | `can_post_first_comment` |
| `src/db/models/publishing.py` | 新列 |
| `static/publish_queue.html` + `publish_queue.js` | 首评状态列 |
| `docs/publishing/douyin_selectors.md` | 评论框 selector |
| `tests/test_first_comment.py` | 核心测试 |

## 非目标

- 自动回复观众留言、楼中楼对话。
- 置顶评论（平台能力不统一）。
- 首评带外链、带商品卡。
- 多版本首评 A/B（P3 可选）。
- 独立于 `PublishJob` 的 `CommentJob` 表（P2 前不建）。
- 修改发布间隔 / 禁发窗逻辑。

## PM 审核记录

- **结论：** 已通过（产品决策）
- **审核日期：** 2026-08-29
- **已确认：**
  1. P0 **仅抖音**
  2. 发布重试时，若首评已 `posted` → **跳过**，不重复发评
  3. 总开关在 **发布中心**，不在系统配置

---

## 首席架构师审阅

> 审阅日期：2026-08-29  
> 审阅人：首席架构师 Agent  
> 结论：**批准进入 P0 实现** — Spike dry-run + `--post` 已于 2026-08-29 通过。

### 0. 审阅结论摘要

| 项 | 结论 |
|----|------|
| 总体评价 | **有条件批准** |
| 架构方向 | 生成侧扩展 `first_comment` + `PublishJob` 状态字段 + 抖音 adapter 自动化，与现有 publishing 垂直切片一致 |
| P0 范围 | **仅抖音**，符合 YAGNI |
| 产品决策 | 发布重试跳过已 `posted` 首评、开关在发布中心 — **采纳** |
| **关键修正** | 首评必须在 `open_adapter_browser` **同一上下文**内完成，不能 orchestrator 二次调 adapter |
| **前置门禁** | `scripts/probe_douyin_first_comment.py` — **已于 2026-08-29 完全通过**（dry-run + `--post`；`manage_row_comment_stat` → `interactive/comment?item_id=`；输入框 `DIV.input-d24X73`） |

### 0.1 审阅发现与处置

| # | 严重度 | 问题 | 修订 |
|---|--------|------|------|
| 1 | **Blocking** | 原稿写「`publish_video` 返回后同会话 `post_first_comment`」；现网 `douyin.py` 在 `with open_adapter_browser` 结束即 `close()` | 首评逻辑移入 `DouyinAdapter.publish_video` 块内，或 `PublishPayload.first_comment` + `post_douyin_first_comment(page, ...)` |
| 2 | **Blocking** | 未定义抖音评论 DOM / 入库延迟路径 | P0 前必须 Spike + `docs/publishing/douyin_selectors.md` 增补评论区 selector |
| 3 | High | 发评轮询最长 60s，Job 保持 `uploading`，阻塞全局串行发布 | 接受 P0；`publish_job_scope` 日志区分「发布中 / 发评中」；P2 再议异步 |
| 4 | High | `PublishResult` 无 `comment_result`，orchestrator 无法原子落库 | 扩展 `PublishResult` 或返回 `PublishOutcome(publish, comment)` |
| 5 | High | DB 迁移：`publish_jobs` 增 5 列 | `init_db` / Alembic 式 `engine.py` 补列；与现网 SQLite 兼容 |
| 6 | Medium | 总开关存哪 | `publishing_platforms.local.yaml` + `GET/PUT` 发布中心 API（镜像 auto_publish settings 模式） |
| 7 | Medium | 非抖音任务带 `first_comment_text` | 入队可快照文案；发评时 `comment_status=unsupported` 或 `skipped`（开关关则为 `skipped`） |
| 8 | Medium | 生成失败 / 合规拒绝时无 `first_comment` | 允许空；`comment_status=none`，不阻断出片与发布 |
| 9 | Low | 成功指标 80% `posted` 在 Spike 前难承诺 | P0 验收改为「Spike 通过 + 人工跑通 3 条」；80% 作 P1 线上指标 |
| 10 | Low | `retry-comment` 新开会话 vs 发布同会话 | P1 独立会话可接受；须复用 `human_pacing` |

### 0.2 架构对齐检查

| 原则 | 评估 |
|------|------|
| 与 ingestion 平行、adapter 封装 Playwright | ✅ |
| Worker 独占浏览器、`browser_lock` | ✅ 发评延长锁持有时间，须监控 |
| 发布失败 vs 发评失败分离 | ✅ |
| 不新增 CommentJob 表（P0） | ✅ 状态字段足够 |
| 内容生成单轮 LLM 增字段 | ✅ 成本低；注意 JSON schema 与 compliance 同步 |
| 配置入口分散 | ⚠️ prompt 在 content_prompts、开关在发布中心 — 文档已写明，可接受 |

### 0.3 Spike 验收标准（实施前）

1. 手动发布一条测试视频后，能在创作者后台「内容管理」找到该作品。
2. 15s 内未找到则轮询至 60s，记录命中率。
3. 定位评论输入框并成功发送一条 20 字以内测试评论。
4. 输出：selector 列表、平均耗时、失败截图路径约定。

### 0.4 修订后 P0 最小交付

1. `first_comment` 生成 + `video_draft_json` + 入队快照  
2. `PublishJob` 字段 + API 响应  
3. 发布中心开关 + `publishing_platforms.local.yaml`  
4. 抖音 `post_douyin_first_comment`（**同会话**）  
5. orchestrator 写 `comment_status`；发布重试跳过 `posted`  
6. 测试：`test_first_comment.py`（mock 为主）+ Spike 脚本人工记录  

**P0 不做：** 快手/视频号/小红书、资讯库编辑首评、`retry-comment` API、队列 UI 列（可 P1）。
