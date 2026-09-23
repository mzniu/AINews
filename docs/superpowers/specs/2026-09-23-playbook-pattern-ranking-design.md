# 素材驱动打法选型（模式库 Agent Ranking）— 设计规格 v1.1

> 日期：2026-09-23  
> 状态：v1.1 — 架构 / 产品双签（附录 A、B）；待 `writing-plans` 拆实现  
> 关联：`docs/superpowers/specs/2026-09-22-playbook-loop-design.md`（学习环、当前打法、归因）  
> 前提：模式卡 v2、`GET /api/copy-agent/patterns`、战报 `pattern_rollups` 已存在

---

## 1. 问题

今天所有「按打法出稿」路径共用 **一个** `current_playbook_version_id`（`CopyAgentSettings`）。模式库从爆款拆卡中沉淀 **多种** 体裁与叙事结构（`genre`、hook、moves），但 **生成口播时不会根据入库素材自动对号入座**。

后果：

- 快讯、数据解读、争议评论共用同一套 `PlaybookVersion.body`，容易出现「像抄摘要」或「腔调不对题材」。
- 战报只能比较「宪法版 vs 某一版全局打法」，无法回答 **「这条素材该用哪类模式、实际选了哪类、效果如何」**。
- 运营在 Pattern Lab 看到模式库增长，但入库侧仍只能点「按**当前**打法出稿」，心智断层。

产品方向（已对齐）：**多种打法并存**；**按素材（标题 + 摘要/正文节选）选型**；「当前打法」保留为 **默认兜底与人工 override**，而非架构上限。

---

## 2. 目标 / 非目标

### 2.1 目标

| # | 目标 |
|---|------|
| G1 | 在调用 `build_video_content_messages(..., playbook_body=...)` **之前**，根据素材从模式库选出 **一个** `playbook_version_id`（及可解释的 `cluster_key`）。 |
| G2 | 选型与写稿 **两次模型调用**：选型轻量、结构化 JSON；写稿沿用现有 `complete(messages)` + `fact_gate`。 |
| G3 | 选型结果 **可审计**：写入 `CopyDraft` / `video_draft_json` 扩展字段，战报可聚合「选型 + 表现」。 |
| G4 | **低置信或校验失败** 时回退 `current_playbook_version_id`（若存在），不阻断出稿；回退原因可展示。 |
| G5 | 第一期库规模 **≤ 40 个聚类** 时，允许 **全量候选** 交给 Agent ranking；预留 **Top-K 预筛** 扩展点。 |

### 2.2 非目标

- 不替代拆卡 Harness；选型任务不写 workspace 文件。
- 不在第一期做 embedding 服务或独立向量库（可作为 P2）。
- 不改变 `fact_gate` / 陷阱检查 / `compose.py` 宪法拼接方式。
- 不自动因「换选型」重渲染历史成片（与 playbook-loop 一致，仍靠「重新出片」）。
- 第一期不做「一次生成 N 稿再人工排序」（战报 spec 里的 N=3 草稿仍属后续）。
- 选型 Agent **不得**读取 `material.txt` 级爆款原文库或仓库外路径。

---

## 3. 核心概念

| 术语 | 定义 |
|------|------|
| **模式聚类** | `list_pattern_library` 的一条：`genre` + `pattern_name`（归一化 key），含 `version_ids[]`、`motives_primary`、`hook_archetype`、`count`。 |
| **cluster_key** | 稳定字符串：`{genre}|{normalized_pattern_name}`，用于 API 与归因。 |
| **代表版本** | 聚类内用于出稿的单个 `playbook_version_id`；见 §5.3。 |
| **选型预览** | 发给 ranking 模型的短结构，来源于 `card_preview_from_stored` 的子集（**显式 `include_evidence=False`**），**不含** `PlaybookVersion.body`。 |
| **全局当前打法** | `settings.current_playbook_version_id`，仅作 **兜底** 与 **`material_adaptive_playbook` 关闭** 时的唯一来源；**不参与** ranking 偏置。 |

---

## 4. 用户场景

### 4.1 资讯库出稿

1. 运营打开文章详情：
   - `material_adaptive_playbook == true`（默认）：主按钮 **「按推荐打法出稿」**；副文案展示上次或预检的 **推荐模式名**（可选 P0：点击后再展示 reason）。
   - `material_adaptive_playbook == false`：主按钮 **「按当前打法出稿」**（与今日一致）。
2. 系统：构建候选 → ranking（可跳过，见 §5.0）→ `generate_one_draft` → fact_gate → 写入 `video_draft_json`。
3. 详情展示：**推荐模式名**、**置信度**、**reason（≤80 字）**。
4. **低置信回退**（黄条，禁止静默）：**「推荐不明显，已用当前打法：{当前模式名或版本标签}」**；链到 Pattern Lab 中当前打法对应条目。
5. **冷启动**：模式聚类 `total < 3` 时，按钮上方灰字：**「模式少于 3 个，建议先在打法学习拆卡；仍会按推荐逻辑尝试。」**（不自动关 adaptive）。
6. **P1**：文章级 **「本条固定用当前打法」** checkbox（`force_current_playbook`），争议稿控口径；写入 article metadata 或 `video_draft_json`。

### 4.2 主页试稿

与 `generate_one_draft` 相同选型逻辑；设置页可关 **「素材自动选型」**（`material_adaptive_playbook`）。

### 4.3 自动出片（双开关）

| 开关 | 默认 | 效果 |
|------|------|------|
| `auto_uses_current_playbook` | 关（playbook-loop） | 开：自动出片读当前打法 body |
| `auto_material_adaptive_playbook` | **关** | 开：在自动出片路径上 **先 ranking 再写稿** |

仅当 **`auto_uses_current_playbook` 与 `auto_material_adaptive_playbook` 同时为开** 时，自动出片才做素材选型。只开前者时行为与今天一致（始终 `current_playbook_version_id` 的 body）。选型失败则退回当前打法 body；再失败走 playbook-loop「宪法版」路径。

打开 `auto_uses` 时，设置页展示二次确认文案：**「自动出片也按素材选打法」** 需单独打开 `auto_material_adaptive_playbook`。

### 4.4 Pattern Lab（只读洞察）

P1：模式库列表增加「近 7 日被选型次数 / 过闸率」。P0：入库详情展示 **本次** `selection_json` 即可。

---

## 5. 选型流水线

### 5.0 何时跳过 ranking

以下情况 **不调用** ranking，直接使用 `current_playbook_version_id`（须 body 非空，否则 `NoPlaybook`）：

- `material_adaptive_playbook == false`（手动路径），或 `auto_material_adaptive_playbook == false`（自动路径）。
- 请求参数 `force_current_playbook=true`（P1 文章级固定）。
- 候选 `total == 0`（无 v2 聚类）：不 ranking；若无当前打法 → **`NoPlaybook`（409）**。

### 5.1 输入

```json
{
  "title": "文章标题",
  "content": "摘要或正文；服务端截断至 max_material_chars（默认 1200）",
  "source_hints": {
    "article_id": "可选",
    "ingestion_source": "可选"
  }
}
```

### 5.2 候选构建 `build_ranking_candidates(session)`

1. 调用 `list_pattern_library(session)`。
2. 对每个聚类，取 **代表卡**：同 genre+name 下 `created_at` 最新且 `is_v2_card` 的 `PatternCard`。
3. 生成 `ranking_preview`（`card_preview_from_stored(..., include_evidence=False)` 子集）：

| 字段 | 说明 |
|------|------|
| `cluster_key` | 必填 |
| `genre_label` | 展示 |
| `pattern_name` | 展示 |
| `purpose` | 模式目的一句 |
| `move_functions` | moves[].function 列表，最多 6 个 |
| `hook_archetype_label` | 钩子原型 |
| `motives_primary_label` | 动机 |
| `verdict_function_label` | 体裁功能 |
| `version_ids` | 封闭集合，供校验 |
| `representative_version_id` | §5.3 解析 |

4. 若 `total == 0`：见 §5.0，**不得**凭空选 top1。

5. 若 `total > ranking_max_candidates`（默认 40）：**P1** 启用 `prefilter_candidates`（§5.6）；P0 可 **409** 并提示「模式过多，请关闭自动选型或联系合并模式」。

### 5.3 代表版本解析 `resolve_representative_version_id(cluster)`

**不得**因 `current_playbook_version_id ∈ version_ids` 而优先当前；当前打法只在 §5.5 回退阶段使用。

优先级（默认）：

1. `version_ids` 中 `PlaybookVersion.status == published` 且 `trap_passed` 的最新 `created_at`。
2. 否则 `version_ids` 中最新 `created_at`。
3. 若无有效 `body` → 该候选从 ranking 列表 **剔除**。

### 5.4 Ranking 调用

- **函数**：`rank_playbook_for_material(session, title, content, complete_rank) -> PlaybookSelection`
- **消息**：system 说明只排序、不写稿、不编造候选；user JSON：`material` + `candidates[]`（仅 preview）。
- **模型**：低 temperature；`PLAYBOOK_RANK_MODEL`（P1）可覆盖。
- **输出 JSON schema**：

```json
{
  "ranked": [
    {
      "cluster_key": "opinion|对照开场",
      "score": 0.0,
      "reason": "不超过 80 字"
    }
  ],
  "chosen_cluster_key": "opinion|对照开场",
  "confidence": "high | medium | low",
  "rejected_cluster_keys": ["可选，1～2 个"]
}
```

- **校验**（`validate_ranking_response`）：
  - `chosen_cluster_key` ∈ 候选 `cluster_key` 集合。
  - `ranked` 长度 ≤ 候选数；`score` ∈ [0,1]。
  - `reason` 长度 ≤ 80。
  - `rejected_cluster_keys` 若有，须为候选子集（可选字段）。

- **映射**：`chosen_cluster_key` → `representative_version_id`；加载 `PlaybookVersion`，`body` 非空。

### 5.5 置信度与回退

| 条件 | 行为 |
|------|------|
| `confidence == high` 且校验通过 | 使用选型 `representative_version_id` |
| `confidence == medium` 且 `top1.score − top2.score ≥ 0.12` | 使用选型版本 |
| 否则 | 使用 `current_playbook_version_id`（若存在且 body 非空），`fallback: true` |
| ranking 解析失败 / 超时（默认 **15s**） | 同上，记 `selection_error`；**不** 以 500 暴露选型超时 |
| 低置信且 **无** current | **`NoPlaybook`（409）** — 不强行使用 top1 |

`PlaybookSelection`：

```python
{
  "playbook_version_id": str,       # 与 CopyDraft.playbook_version_id 一致
  "cluster_key": str | None,        # 推荐簇；fallback 时可为 null
  "pattern_name": str | None,
  "genre_label": str | None,
  "confidence": str,
  "reason": str,
  "fallback": bool,
  "recommended_version_id": str | None,  # ranking 选中但未采用的版本
  "fallback_used_version_id": str | None,
  "policy_version": "rank-v1",
  "ranking_json": str,
}
```

### 5.6 预筛扩展（P1）

`prefilter_candidates(candidates, title, content, k=12)`：规则分 + n-gram；再送 Agent ranking。第一期不实现 embedding。

### 5.7 防抖与短时复用

- UI：出稿按钮 **防抖**（例如 2s 内忽略重复点击）。
- 服务端：**可选** 60s 内相同 `sha256(title + "\n" + content)` 复用该文章最近一条 `CopyDraft.selection_json` 解析出的 `PlaybookSelection`（同 `article_id` 优先），避免连点 double ranking。实现可 P0 仅防抖，缓存 P1。

---

## 6. 与现有模块集成

### 6.1 `services/copy_agent/drafts.py`

- `generate_one_draft(..., force_current_playbook: bool = False)`。
- adaptive 开启时先 `rank_playbook_for_material`；否则用 current。
- `CopyDraft.playbook_version_id` **必须**等于实际写稿所用版本；`selection_json` 记录推荐与 fallback 字段（§5.5）。

### 6.2 `services/ingestion/playbook_draft.py`

无签名变更；经 `generate_one_draft` 获得选型。

### 6.3 `services/ingestion/media_pipeline.py`

仅当 `auto_uses_current_playbook` **且** `auto_material_adaptive_playbook` 为真时，在 `generate_video_content` 前 ranking；否则仅用 current body。

### 6.4 `services/copy_agent/compose.py`

不变。

### 6.5 战报 `battle_report.py`

stamp 含 `pattern_cluster_key` 时纳入 `pattern_rollups`；P0 增加 **`selection_fallback` 计数**；pattern 归因以 **实际写稿** `playbook_version_id` 为准，fallback 时不用 `recommended_version_id` 计入口径。

---

## 7. 数据模型变更

### 7.1 `copy_drafts.selection_json`

```json
{
  "policy_version": "rank-v1",
  "cluster_key": "data|数字冲击开场",
  "pattern_name": "数字冲击开场",
  "genre": "data",
  "confidence": "high",
  "reason": "...",
  "fallback": false,
  "recommended_version_id": "…",
  "fallback_used_version_id": null,
  "ranked_top3": [{"cluster_key": "...", "score": 0.82}]
}
```

### 7.2 `video_draft_json` / publish stamp

```json
{
  "playbook_version_id": "...",
  "pattern_cluster_key": "...",
  "pattern_name": "...",
  "playbook_selection_confidence": "high",
  "playbook_selection_fallback": false
}
```

### 7.3 `copy_agent_settings`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `material_adaptive_playbook` | bool | **true** | 手动出稿 / 主页试稿是否素材选型 |
| `auto_material_adaptive_playbook` | bool | **false** | 自动出片是否素材选型（需与 `auto_uses` 同时开） |
| `ranking_max_candidates` | int | 40 | 超过则 P0 409 或 P1 预筛 |

SQLite migration：`src/db/engine.py`。

---

## 8. API

### 8.1 内部

`rank_playbook_for_material(session, title, content, complete_rank)`。

### 8.2 `POST /api/copy-agent/rank-preview`（P1）

不写库、不写稿；返回 `PlaybookSelection` + `candidates_count`。

### 8.3 设置 `PATCH /api/copy-agent/settings`

返回/接受：

- `material_adaptive_playbook`
- `auto_material_adaptive_playbook`（文案见 §4.3）
- `ranking_max_candidates`

---

## 9. 配置与环境

| 变量 | 默认 | 说明 |
|------|------|------|
| `PLAYBOOK_RANK_TIMEOUT_SEC` | **15** | 选型超时后回退 |
| `PLAYBOOK_RANK_MAX_MATERIAL_CHARS` | 1200 | 素材截断 |
| `PLAYBOOK_RANK_MODEL` | 同写稿模型 | P1 |

---

## 10. 测试策略

| 用例 | 类型 |
|------|------|
| `validate_ranking_response` 拒绝非法 cluster_key | 单元 |
| `resolve_representative_version_id` 不用 current 偏置 | 单元 |
| 候选含空 body 版本被剔除后 ranking 仍合法 | 单元 |
| 低置信 + 有 current → fallback，`recommended_version_id` ≠ 写稿 id | 单元 |
| 无候选且无 current → `NoPlaybook` | 单元 |
| 双开关：仅 `auto_uses` 开 → 不 ranking | 集成 |
| stamp 含 `pattern_cluster_key`；fallback 战报口径 | 集成 |

禁止 CI 调用真实 ranking 模型。

---

## 11. 分阶段交付

| 阶段 | 内容 |
|------|------|
| **P0** | ranking 纯函数、`selection_json`、`generate_one_draft`、双开关与默认值、入库按钮/黄条/冷启动文案、战报 fallback 列 |
| **P1** | `rank-preview`、预筛 Top-K、`PLAYBOOK_RANK_MODEL`、文章 `force_current`、60s 复用、Pattern Lab 统计列 |
| **P2** | embedding 预筛、低置信双稿择优 |

---

## 12. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Token 随模式库增长 | 预览上限；>40 预筛或 409 |
| 幻觉 cluster | 封闭校验；回退 |
| latency | 15s 超时；防抖 |
| 自动出片风格突变 | `auto_material_adaptive` 默认关 |
| 磁盘/DB 满 | 507/运维；与选型无关 |

---

## 13. 成功指标（产品）

- 分 **genre** 的过闸率相对单打法 baseline 提升。
- `selection_fallback` 占比 < 30%。
- P0 战报可见 fallback 计数；≥3 个 pattern 有样本后可读分享率差异。

---

## 附录 A — 首席架构师 Review（v1 → v1.1）

**结论**：**通过**（Blocking 项已合入正文 v1.1）

已落实：代表版本去 current 偏置；`recommended` / `fallback_used` 分离；空库无 current → `NoPlaybook`；15s 超时；§5.7 防抖/缓存；ranking payload 禁止 excerpt。

保留建议（非阻塞）：`rejected_cluster_keys` 已写入 §5.4 可选字段。

---

## 附录 B — 首席产品经理 Review（v1 → v1.1）

**结论**：**P0 范围批准**

已落实：推荐/当前按钮文案、低置信黄条、冷启动灰字、`auto_material_adaptive` 双开关默认关、P1 文章固定当前打法。

P0 签核清单：

- [x] 按钮与黄条文案定稿（§4.1）
- [x] `material_adaptive` 默认 true；`auto_material_adaptive` 默认 false（§7.3）
- [x] 少模式弱提示（§4.1）
- [x] 架构 Blocking 合入 v1.1

---

## 附录 C — 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 Draft | 2026-09-23 | 初稿 + 附录 A/B 审阅 |
| v1.1 | 2026-09-23 | 合入架构/产品 Blocking；双开关；§5.0/5.7；指标与测试更新 |

---

*实现前请 invoke `writing-plans` 拆任务。*
