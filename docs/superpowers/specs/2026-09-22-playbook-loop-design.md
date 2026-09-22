# 打法学习与自动出片 — 设计规格 v3

> 日期：2026-09-22
> 状态：v3 Draft
> 取代：同文件 v2
> 不改：`should_run_media_pipeline` 的等级与分数、`auto_publish.min_grade`、`content_prompts.yaml`、`/api/generate-summary` 的默认行为

产品决定：**DeepSeek Harness（`dsh`）留在第一期。** 接受同用户进程可以读到该用户能读的磁盘。路径审计只决定这次拆卡结果能不能入库，不是安全边界。

## 1. 问题

文案有两个调用点，提示词都来自 `config/content_prompts.yaml` 与 `utils/content_methodology.py::build_methodology_prompt_section`，但不是同一个函数：

- 主页 `/api/generate-summary`：`api/routes/crawler_routes.py::generate_summary` 内联拼装，`task="crawler_content"`。
- 自动出片：`services/ingestion/media_pipeline.py` 调用 `services/content_generation_service.py::generate_video_content`，`task="content_gen"`，多一个 `first_comment`。口播长度以 `run_media_pipeline` 传入的 `voiceover_min_chars` / `voiceover_max_chars` 为准（配置默认 40 / 90），不是函数签名上的 70 / 90。

打法不得写入 `build_methodology_prompt_section`。不变式要分别对两个调用点做快照。

爆款样本和线上转发现在进不了这套提示词。把爆款原文写进宪法，会把无出处比较级带进自动口播。

自动出片在开关关闭时保持今天的链路：

```
评分达标
  → maybe_enqueue_media_job（should_run_media_pipeline，默认 S 或 ≥80）
  → run_media_pipeline
  → generate_video_content          # 不读打法
  → maybe_enqueue_auto_publish_jobs（score_grade ≥ min_grade，默认 S）
  → PublishJob                      # playbook_attribution 为空
```

## 2. 目标 / 非目标

**目标**

- 第一期就能走完：贴屏幕文案 → `dsh` 拆成一版打法 → 人发布为「当前打法」→ 主页按它出一稿并写入现有编辑框。
- 当前打法上有一个默认关闭的开关「自动出片也用这一版」。打开前必须通过陷阱检查。
- 自动出片闸门失败时退回无打法生成，成片和自动发布不中断，该条在资讯库标成「打法未过闸，已用宪法版」。
- 战报用 `playbook_attribution` 区分宪法版、打法稿、人工改稿、闸门退回和生成失败。只有 `playbook` 进入升降。

**非目标**

- 不微调模型，不把 Claude Code 或 Pi 打进安装包。
- 不让 Harness 修改仓库或 `content_prompts.yaml`。
- 不改变评分门槛和自动发布等级。
- 不改写已入队的 `PublishJob`。换打法不自动重渲染已有成片；要另点「按当前打法重新出片」。
- 第一期不接 GitHub 视频制作，不把 `dsh` 打进 Tauri 安装包。
- 第一期不做三稿排序、不做满 8 条才允许下一轮、不做两个互相独立的版本指针。
- 第一期不做进程隔离，不把目录 ACL 当成安全边界。

## 3. 当前打法，一个开关

只有一个当前版本 `current_playbook_version_id`。

| 开关 | 默认 | 效果 |
|---|---|---|
| 自动出片也用当前打法 `auto_uses_current_playbook` | 关 | 开：此后新进入成片的稿使用当前版本。关：`generate_video_content` 与现在一致 |

发布新版本不会自动打开这个开关。

开关为关时，陷阱检查失败仍可发布为当前打法，页面用红字展示失败句，供主页试稿。

开关为开时，发布新版本前先跑陷阱检查。不通过则 409，当前版本和开关都不变。响应与红字必须同时包含这句：「自动出片还开着，所以这一版不能换上去。先关掉「自动出片也用这一版」，就能发到主页试。试过之后再打开。」错误体带 `hint=disable_auto_switch`。通过则当前版本换成新版，开关保持开，此后新成片跟随新版。

已渲染的视频不跟随。资讯库提供「按当前打法重新出片」：强制 `generate_content=true`，走第 7 节状态机。这和 `build_manual_media_retry_config` 不同——后者在已有 `video_draft_json` 时会把 `generate_content` 设为 false。

## 4. 学习环

### 4.1 输入

主入口只有「贴屏幕文案」。链接和截图是附件，不触发拆解，界面上不作为主按钮。没有正文则任务停在 `needs_text`，不启动 `dsh`。

`share_style`、两类卡互斥检索，第一期不做。

### 4.2 实现约束（不上界面）

第一期使用 DeepSeek Harness。桌面端同时只跑一个拆卡任务，已有 `running` 则 409。

每次任务的工作目录是数据目录下的 `copy_agent/workspaces/{job_id}/`，只放 `material.txt`、`schema.md`、空的 `drafts/`。`session_id` 等于 `job_id`。会话日志放在 `copy_agent/sessions/{job_id}/`。`cwd` 不是仓库根。提示词里不出现仓库路径、`.env` 路径或其他任务的目录。

子进程环境变量白名单：`PATH`、`SYSTEMROOT`、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`，以及 `dsh` 启动所必需的变量。其余变量不继承。这只减少无关密钥进子进程，不阻止同用户读盘。

系统提示词覆盖默认的软件工程师人设：只写 `drafts/card.yaml` 和 `drafts/playbook.diff.yaml`；`verdict.kind` 必须是 `opinion`；无出处比较级写入 `forbidden_transfers`。超时 180 秒。

跑完后的路径审计只服务入库：

1. 解析会话 JSONL。工具参数里的路径必须落在该 `job_id` 的 workspace 或 session 目录内。越界则丢弃 yaml，状态 `rejected_escape`，不能发布。
2. Pydantic 校验。`verdict.kind != opinion` 则 `rejected_schema`，不能发布。

接受的残余风险：进程与桌面应用是同一 Windows 用户，运行中可以读该用户能读的磁盘，也可以在 180 秒内使用环境中的 `DEEPSEEK_API_KEY`。路径审计不阻止这些行为，只避免把越界那一次的卡片和 diff 写入数据库。界面不展示本节术语。

### 4.3 未安装 `dsh`

导航仍显示「打法学习」。未检测到 `dsh` 时不显示贴文框。页面只有三行产品文案：

1. 状态：「还不能拆爆款。未检测到 dsh。」
2. 下一步：页上一条安装命令，以及按钮「重新检测」。
3. 成功：检测变为「可以拆卡」，贴文框出现。失败时只重复失败原因和同一条安装命令。

### 4.4 模式卡与 diff

出稿只看槽位。`evidence_excerpt` 和禁迁项原文不进入出稿提示词。禁迁项变成约束类别，例如「禁止无出处的倍数升级」。

`motives` 取值与 `viral_scorer` 的四类一致，第一期只展示，不参与检索。没有「当前打法」时，主页按钮不可点。接口若被调用，返回 409 `no_playbook`，不调用模型。

拆卡成功后，发布按钮可直接点。页面默认一句：「这次只写了草稿目录里的文件。」工具路径放在折叠的「查看详情」里，不作为发布条件。`rejected_escape` 时不显示这句，改为：「这次写到了草稿目录外面，结果已丢弃。」详情仍默认折叠。

### 4.5 陷阱检查

固定陷阱题一条：原文约 8 倍，输出不得写成 10 倍；原文无评测表，不得出现「全面超越」。纯函数判定，不另叫模型当裁判。

- 开关为关：陷阱失败仍可发布，红字展示失败句。
- 打开开关：陷阱失败则拒绝打开。
- 开关为开时发布新版本：陷阱失败则 409，文案见第 3 节。

另外两条回放题（有对照、无对照）放到第二期，不阻塞第一期发布。

## 5. 提示词怎么拼

新建 `services/copy_agent/compose.py`，主页打法出稿和自动出片共用。不修改 `build_methodology_prompt_section` 的函数体。

```
system = get_system_role()          # 只有宪法
user   = build_methodology_prompt_section(...)
         + 可选的打法正文            # 仅当传入 playbook_body 非空
```

`generate_video_content(..., playbook_body: str | None = None)`：`playbook_body` 为空时，消息与今天一致，不得读打法表。

`/api/generate-summary` 不接受打法参数，不读打法表。主页「按当前打法出稿」走 `POST /api/copy-agent/drafts`，内部调用 `compose.py`。

## 6. 主页

保留「生成 AI 标题和摘要」和「一键生成视频」。这两条路径的 `playbook_attribution` 为空。

新增「按当前打法出稿」。没有当前打法时按钮禁用，文案指向打法学习页。有则异步出 **1** 稿（第一期 N=1）。事实闸门不通过的稿可以看、不能写入编辑框。通过后写入现有标题、口播、标签输入框，并记录 `copy_draft_id`。此时草稿的归因为 `playbook`。

选用后用户改了字：草稿归因改为 `edited`，`playbook_version_id` 和 `copy_draft_id` 都保留。界面显示「这版打法，之后改过」。战报不把它算进升降（第 8 节）。

## 7. 自动出片状态机

`run_media_pipeline` 的 `generate_content` 步骤把归因写进 `video_draft_json`：

1. `auto_uses_current_playbook` 为关，或当前版本为空：调用现有 `generate_video_content()`。不写 `playbook_version_id`，不写 `playbook_attribution`。
2. 开关为开：用 `compose.py` 出 1 稿（N=1，与主页同一函数）。
   - 事实闸门通过：`playbook_attribution=playbook`，`playbook_version_id` 为当前版本 id。
   - 事实闸门不通过：再调用不带打法的 `generate_video_content()`。`playbook_attribution=fact_gate_fallback`，`playbook_version_id` 为空。资讯库该条显示「打法未过闸，已用宪法版」。然后继续配图、渲染和自动发布判断。
3. 任一次模型调用抛错：沿用今天的 `except`。已有草稿则复用，否则 `_fallback_draft`。`playbook_attribution=generation_fallback`，`playbook_version_id` 为空。界面沿用现有成片状态，并加上「打法生成失败，已用原有回退」。

第二期若改为 N=3：只在事实闸门通过的稿里取规则分最高的一稿。规则分是纯函数：前 12–16 字含主体、数字、冲突得 1；有对照得 1；有观点句得 1。第一期不实现这条。

事实闸门：数字、倍数、时间跨度、排名、比较级必须在 `title + content` 里有连续依据。7.8 写成 10、无评测却写「全面超越」，判失败。

## 8. 发布记录与战报

归因是 `PublishJob.playbook_attribution`，不是靠版本号是否为空来猜。

| `playbook_attribution` | `playbook_version_id` | `copy_draft_id` | 战报 |
|---|---|---|---|
| `NULL` | `NULL` | `NULL` | 宪法版。不进升降，不进「再学」摘要 |
| `playbook` | 必填 | 必填 | 计入该版本升降，可进入「再学」摘要 |
| `edited` | 必填（被改的那一版，只供展示） | 必填 | 标「人工改稿」。不进升降，不进「再学」摘要 |
| `fact_gate_fallback` | `NULL` | `NULL` | 标「打法未过闸」。不进升降 |
| `generation_fallback` | `NULL` | `NULL` | 标「打法生成失败」。不进升降 |

禁止写入字符串 `constitution`。`stamp_playbook` 要么按上表写齐三列，要么三列都留空。禁止只把版本号写成空、让战报再去猜原因。

新建 `services/publishing/playbook_stamp.py::stamp_playbook(job, source)`。`source` 来自文章 `video_draft_json`，或来自主页发布请求体里的同名字段。每个会 `session.add` 的 `PublishJob(...)` 在添加之前调用一次。

生产构造点：

- `services/publishing/auto_publish.py::create_ingestion_publish_job`。`candidate_queue` 只经这个函数入队，不另建 `PublishJob`，因此盖在这里即可。
- `services/publishing/platform_jobs.py::_create_job_for_platform`。
- `api/routes/publishing_routes.py` 创建任务处（约第 297 行）。请求体可带 `playbook_version_id`、`copy_draft_id`、`playbook_attribution`；未带时，若 `source_id` 指向已入库文章，则读该文的 `video_draft_json`。

`services/publishing/orchestrator.py` 里的 `probe_job` 不入库，不调用 `stamp_playbook`。

`draft_from_video_draft` 继续只抽标题和描述，不负责抄归因。

战报由 `publish_jobs` 与发布后 72 小时内最近一条 `PublishPostMetricSnapshot` 聚合。升降和「再学」摘要只使用 `playbook_attribution='playbook'`。

`like_count` 为 NULL 或 0：不计算转发/赞，该行只显示转发数，标记「无赞，未算比率」。不因此丢行。播放量不参与。平台分行展示，也提供不分平台的列表。

第一期「带着这些结果再学」只要存在至少一条 `playbook` 归因的发布就可以点。不要求 8 条，不要求相对近 30 条基线。点下去只把这些 `playbook` 行的版本、平台、转发、赞（比率仅在赞大于 0 时附上）写进下一次沙箱的 `battle_report.md`。没有这样的行时，按钮不显示。

近 30 条基线和「满 8 条」不作为第一期资格。第二期可以在战报上显示相对基线，仍不作为按钮开关，除非另开规格。

## 9. 数据模型

| 表或列 | 字段 |
|---|---|
| `copy_agent_settings` | 单行：`current_playbook_version_id` 可空，`auto_uses_current_playbook` 布尔默认 false |
| `playbook_versions` | `parent_id`，`body`，`diff_json`，`status=candidate\|published\|retired`，`trap_passed` 布尔 |
| `pattern_cards` | 槽位、`forbidden_transfers`、`evidence_excerpt`、`status`、`source_job_id` |
| `copy_agent_jobs` | `kind=curate\|draft`，`status`，`session_id`，`workspace_path`，`result_json` |
| `copy_drafts` | 稿 JSON、`fact_gate_json`、`playbook_version_id`、`selected`、`edited_after_select` |
| `PublishJob` 新列 | `playbook_version_id` 可空，`copy_draft_id` 可空，`playbook_attribution` 可空 |

`IngestedArticle.video_draft_json` 使用与 `PublishJob` 相同的三个归因字段。没有这些键等于宪法版。

## 10. API

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/copy-agent/materials` | 正文必填。链接、截图仅附件 |
| GET | `/api/copy-agent/jobs/{id}` | 轮询。成功时带一句目录内结论；失败时带丢弃原因。路径列表在详情字段，不作为发布条件 |
| GET | `/api/copy-agent/harness` | 检测 `dsh`。返回 `ready` 与给页面用的三行文案 |
| POST | `/api/copy-agent/versions/{id}/publish` | 设为当前打法。开关已开且陷阱失败则 409，`hint=disable_auto_switch` |
| POST | `/api/copy-agent/auto-switch` | `{ "enabled": true }` 在陷阱未过时 409 |
| POST | `/api/copy-agent/drafts` | 主页 1 稿。无当前打法则 409 `no_playbook` |
| POST | `/api/copy-agent/drafts/{id}/select` | 写入选用；之后编辑把归因改为 `edited`，版本号保留 |
| POST | `/api/ingestion/articles/{id}/rerender-playbook` | 按当前打法重新出片 |
| GET | `/api/copy-agent/battle-report` | 只读聚合，含归因标签 |

创建发布任务的现有接口增加可选字段 `playbook_version_id`、`copy_draft_id`、`playbook_attribution`。`/api/generate-summary` 不改。

## 11. 前端

- 导航「打法学习」。未安装时只显示第 4.3 节的三行，不出现贴文框，不出现白名单或 JSONL 字样。
- 装好之后一条流程：贴文 → 看模式卡和 diff → 发布为当前打法。默认一句「这次只写了草稿目录里的文件。」陷阱失败用红字，不挡发布。开关为开且陷阱失败时，红字包含第 3 节那句「先关掉自动出片」。
- 当前打法旁一个开关「自动出片也用这一版」，默认关。陷阱未过时开关禁用并说明原因。
- 主页按钮在无当前打法时禁用。主页发布把当前编辑区的归因字段带上。
- 资讯库对「打法未过闸，已用宪法版」和「打法生成失败，已用原有回退」用现有任务状态行展示，不新做仪表盘。
- 设置「标题文案」加一句：打法不写在这里。

## 12. 分期

**第一期（本规格的完成定义）**

1. 表、`stamp_playbook` 覆盖第 8 节列出的生产构造点、环境变量白名单、路径越界则不入库。
2. 贴文 → `dsh` → 发布当前打法。未安装页按第 4.3 节验收。
3. 主页 1 稿、事实闸门、选用写入现有编辑框。改稿后归因为 `edited`。
4. 自动开关默认关。打开后走第 7 节。资讯库可见退回。另有「按当前打法重新出片」。
5. 战报只读，「带着这些结果再学」只统计 `playbook` 归因，无条数门槛。

**第二期**

- 有对照 / 无对照回放题。
- 主页和自动出片 N=3 与第 7 节的规则分。
- 战报上的相对基线，仅展示。

## 13. 测试

- `verdict.kind` 不是 `opinion`，或工具路径在沙箱外：不入库，发布接口拒绝该任务。
- 子进程环境不含白名单以外的变量。
- 陷阱失败：开关为关时可以发布；不能打开自动开关。开关为开时发布新版本返回 409，且文案含「先关掉」。
- 无当前打法：`/drafts` 不调用模型。
- 自动开关关：`generate_video_content` 的消息与今天一致；`/api/generate-summary` 的消息与今天一致。两份快照分开断言。
- 自动开关开且闸门失败：`playbook_attribution=fact_gate_fallback`，版本号为空，仍进入现有自动发布判断，资讯状态含「打法未过闸」。
- 模型抛错：`playbook_attribution=generation_fallback`，版本号为空。
- `edited`：版本号和 `copy_draft_id` 都保留，战报标人工改稿，不进入升降和「再学」摘要。
- `like_count` 为 0 或 NULL：战报有该行，无比率。
- `create_ingestion_publish_job`、`platform_jobs._create_job_for_platform`、`publishing_routes` 创建任务三处都调用 `stamp_playbook`。`probe_job` 不调用。新列为空时现有自动发布测试仍通过。
- 切换开关或发布新版本后，已入队任务的归因三列不变。

## 14. 复审意见的处理

| 意见 | v3 |
|---|---|
| `dsh` 留在第一期，但第 4.2 节不能称作进程边界 | 接受同用户可读盘。路径审计只丢弃脏入库。本节标明不上界面 |
| `stamp` 把改稿写成空版本号后，战报无法标「人工改稿」 | 增加 `playbook_attribution`。`edited` 保留版本号与 `copy_draft_id`，升降只认 `playbook` |
| 漏掉 `publishing_routes.py` 的 `PublishJob` | 列入构造点。`candidate_queue` 只经 `create_ingestion_publish_job`。`probe_job` 排除 |
| 未安装页没有可执行的三步 | 第 4.3 节写死状态、重新检测、贴文框出现 |
| 看工具路径才能发布 | 默认一句结论。越界由系统丢弃，不要求人读路径 |
| 开关开着时陷阱失败，没有解脱说明 | 409 与红字写明先关掉开关再发到主页试 |
