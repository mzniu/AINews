# 事实闸门 Agent 化 — 设计规格 v1.0

> 日期：2026-09-24  
> 状态：Deferred — 产品默认关闭事实闸门（`CopyAgentSettings.fact_gate_enabled=false`）；规则闸保留可重开，Agent 方案待后续启用闸门时再实施。  
> 关联：  
> - `docs/superpowers/specs/2026-09-22-playbook-loop-design.md`（过闸回退、`fact_gate_fallback`、战报归因）  
> - `docs/superpowers/specs/2026-09-23-playbook-pattern-ranking-design.md`（选型 + 写稿 + 闸门三次调用）  
> 取代：playbook-loop / pattern-ranking 中对 **规则型** `fact_gate(draft, source)` 的约定（§ 数字子串匹配）；**不取代** 打法发布前的 `trap_check`（见 §9）

---

## 1. 问题

当前 `services/copy_agent/fact_gate.py::fact_gate` 用 **零模型、字面规则**（数字子串、`N倍`、`全面超越`）判断打法稿是否可选用。与产品 spec「素材中有依据」相比过严，导致大量 `fact_gate_fallback`、打法参与率低；与「三天 / 3 天」等合理改写相比又无法表达语义支持。

产品方向（本次）：**过闸判定完全由 Agent 完成**，不再用规则引擎做 draft 事实核对。仍保留结构化 JSON、可审计字段与现有归因语义（`playbook` vs `fact_gate_fallback`）。

---

## 2. 目标 / 非目标

### 2.1 目标

| # | 目标 |
|---|------|
| G1 | `generate_one_draft` 在写稿完成后调用 **`fact_gate_agent`**（一次 LLM，结构化 JSON），结果写入 `CopyDraft.fact_gate_json`。 |
| G2 | **`draft_selectable`** 仍只读 `fact_gate_json.passed`；自动出片、主页选用、API `selectable` 行为不变。 |
| G3 | 未过闸时展示 **Agent 给出的可读原因**（`summary` + `issues[]`），替代规则 `violations` 列表。 |
| G4 | 测试路径注入 `complete_fact_gate`，**从不打真模型**（与 `complete_rank` 一致）。 |
| G5 | 模型/合规失败时 **fail-closed**：视为未过闸，不静默当通过（避免幻觉稿进战报 `playbook` 归因）。 |

### 2.2 非目标

- 不用规则函数实现 draft 过闸（**删除或停用** `fact_gate` 的数字/倍数/全面超越子串逻辑；见 §8 迁移）。
- 不改变 `fact_gate_fallback` / `generation_fallback` 状态机、stamp、战报升降规则。
- 不在第一期做「Agent 自动改稿再过闸」；失败仍走现有宪法版第二次 `generate_video_content`。
- 不把 Harness / 模式卡 evidence 并入闸门上下文（仅 `title + content` 与稿内口播字段）。
- 不替代 **`trap_check`**（发布为当前打法前的固定陷阱题，§9）。

---

## 3. 概念

| 术语 | 定义 |
|------|------|
| **素材正文** | `source_text = title + "\n" + content`，服务端截断至 `FACT_GATE_MAX_SOURCE_CHARS`（默认 4000，与 ranking 1200 独立）。 |
| **待核稿文** | `draft_prose = _prose_for_gate(body_json)`（与今日一致：口播/标题等字符串字段拼接，不含 JSON 键名）。 |
| **过闸** | Agent 返回 `passed: true` 且校验通过。 |
| **issue** | 一条不被素材支持的表述，含类型、稿中摘录、理由、可选素材对照摘录。 |
| **policy** | `fact-gate-v1` — 写入 `fact_gate_json.policy_version`。 |

---

## 4. 用户可见行为（与今日对齐）

| 场景 | 行为 |
|------|------|
| 主页「按推荐/当前打法出稿」 | 稿入库；`selectable=false` 时仍 **可查看**，不能写入编辑框。 |
| 自动出片 | `passed=false` → `fact_gate_fallback` + 宪法版；资讯库展示 **Agent summary**。 |
| Pattern Lab / API | `GET` 稿详情返回 `fact_gate` 对象（schema 扩展，§6）。 |

文案示例（未过闸）：

> 打法未过闸，已用宪法版：口播中的「快 10 倍」在素材中无依据；「全球第二」与标题 Terminal-Bench 表述不一致。

---

## 5. 流水线

### 5.1 调用点（唯一生产入口）

```
generate_one_draft
  → complete(messages)           # 写稿
  → fact_gate_agent(             # 新增：仅此过闸
        draft_prose,
        source_text,
        complete_fact_gate,
     )
  → CopyDraft.fact_gate_json
```

`media_pipeline._generate_pipeline_draft` **不**二次调用 Agent；继续 `draft_selectable(copy)` + 读已存的 `fact_gate_json`。

### 5.2 与 ranking 的关系

典型自动出片（双开关开）调用序：

1. `rank_playbook_for_material`（选型）  
2. `complete`（写稿）  
3. **`fact_gate_agent`（过闸）**  

共 **3** 次 LLM。可通过 `PLAYBOOK_FACT_GATE_MODEL` 使用更小/更快模型以控成本。

### 5.3 Prompt 原则（system）

Agent **只审核、不改写**。依据范围 **仅限** 提供的 `source`；允许：

- 同义改写、合理概括（「三天」↔「3 天」）若语义被素材支持 → **通过**  
- 数字/排名/倍数/时间跨度/比较结论 → 须在素材中有 **明确或合理推断** 依据；无依据 → **issue**  
- 打法腔调、修辞、观点句 → 不单独判失败，除非夹带 **无依据事实主张**

禁止：

- 引用素材外知识、联网、猜测「行业惯例」  
- 输出改稿正文  

（实现上写在 system prompt；**不**用代码规则补刀。）

### 5.4 User 消息结构

```json
{
  "source": {
    "title": "...",
    "content": "..."
  },
  "draft": {
    "prose": "从 title/summary/voiceover_script 等拼接的全文"
  },
  "checklist": [
    "数字、百分比、排名、时间长度是否与素材一致或可合理概括",
    "倍数、比较级、绝对化结论是否有素材依据",
    "是否出现素材未提及的实体、产品名、榜单名次",
    "口播是否捏造评测结论或「全面超越」类无出处断言"
  ]
}
```

`checklist` 为 **提示 Agent 的审核维度**，不是代码规则。

### 5.5 输出 JSON Schema

```json
{
  "passed": true,
  "confidence": "high | medium | low",
  "summary": "不超过 120 字；passed=false 时必填",
  "issues": [
    {
      "kind": "number | multiple | ranking | time_span | comparison | entity | other",
      "draft_excerpt": "稿中原文短摘录，≤80 字",
      "reason": "为何素材不支持，≤120 字",
      "source_excerpt": "若有则填素材中相关句，≤120 字；无则空字符串"
    }
  ]
}
```

**校验**（`validate_fact_gate_response`）：

- `passed` 为 boolean。  
- `passed === false` 时 `summary` 非空；`issues` 至少 1 条。  
- `passed === true` 时 `issues` 必须为空数组。  
- `confidence` ∈ {high, medium, low}。  
- 每条 `issue.kind` 在枚举内；各字符串长度上限。  
- 校验失败 → 视为 **闸门失败**（`passed: false`，`summary` 写「闸门响应无效」），`issues` 可空。

**选型策略（可选 P1）**：`confidence === low` 且 `passed === true` 时仍 **通过**（与 ranking 不同）；若产品要更严，可在 settings 加 `fact_gate_require_high_confidence`（默认 false）。第一期 **不实现**。

### 5.6 生产调用

- 函数：`production_fact_gate_complete(messages) -> str`  
- 实现：与 `production_rank_complete` 相同模式 — `invoke_json_llm_with_compliance`，`task="playbook_fact_gate"`，`temperature=0.1`，`max_tokens=768`，`response_format=json_object`。  
- 环境变量：`PLAYBOOK_FACT_GATE_MODEL`（默认同内容生成模型）。

### 5.7 可注入接口

```python
FactGateComplete = Callable[[list[dict]], str]

def fact_gate_agent(
    draft_prose: str,
    source_text: str,
    complete_fact_gate: FactGateComplete,
    *,
    title: str = "",
    content: str = "",
) -> dict:
    """Returns normalized fact_gate_json dict (always includes policy_version)."""
```

`generate_one_draft(..., complete_fact_gate: FactGateComplete | None = None)`：

- 生产：`complete_fact_gate=production_fact_gate_complete`  
- 测试：mock 返回 JSON 字符串  
- `complete_fact_gate is None`：**fail-closed** `{passed: false, summary: "未配置事实闸门", ...}`（仅测试或误配；生产路径必须注入）

### 5.8 异常与超时

| 情况 | 处理 |
|------|------|
| LLM 超时/网络/合规拒绝 | `passed: false`，`summary` 为错误摘要，`issues: []`，`gate_error: "..."` |
| JSON 解析失败 | 同上 |
| validate 失败 | 同上，`gate_error: "invalid_schema"` |

**不**回退到规则 `fact_gate`。  
**不**因闸门失败阻断出片（自动路径仍宪法版）。

---

## 6. 存储与 API

### 6.1 `fact_gate_json` 形态（v1）

```json
{
  "policy_version": "fact-gate-v1",
  "passed": false,
  "confidence": "high",
  "summary": "人类可读一句",
  "issues": [ { "kind": "multiple", "draft_excerpt": "...", "reason": "...", "source_excerpt": "" } ],
  "gate_error": null
}
```

兼容：旧稿仅有 `violations` 时，`draft_selectable` 仍读 `passed`；UI `fact_gate_summary()` 优先 `summary`，其次拼接 `issues`。

### 6.2 `video_draft_json` 扩展（保持现有键）

继续写入：

- `fact_gate_reason` ← `summary` 或 `fact_gate_summary(gate)`  
- `fact_gate_violations` ← 第一期可改为 `issues[].reason` 或 `draft_excerpt` 的字符串列表（UI 不区分来源）

### 6.3 API

`copy_agent_routes` 返回的 `fact_gate` 为完整对象；`selectable` 逻辑不变。

---

## 7. 配置

| 项 | 默认 | 说明 |
|----|------|------|
| `FACT_GATE_MAX_SOURCE_CHARS` | 4000 | 素材截断 |
| `FACT_GATE_MAX_DRAFT_CHARS` | 2500 | 稿 prose 截断 |
| `PLAYBOOK_FACT_GATE_MODEL` | 同内容模型 | 闸门专用模型 |

`CopyAgentSettings` **第一期不加开关**（始终 Agent）；若需回滚，仅部署层保留 `fact_gate.py` 旧函数供 hotfix，不在 UI 暴露。

---

## 8. 代码变更范围（实现计划摘要）

| 文件 | 变更 |
|------|------|
| `services/copy_agent/fact_gate.py` | 保留 `trap_check`；新增 `fact_gate_agent`、`validate_fact_gate_response`、`fact_gate_summary`（读新 schema）；**移除**规则 `fact_gate` 或标 deprecated 并删除调用 |
| `services/copy_agent/drafts.py` | 写稿后调 `fact_gate_agent`；签名增加 `complete_fact_gate` |
| `services/ingestion/media_pipeline.py` | 传入 `production_fact_gate_complete`；fallback 展示用新 summary |
| `api/routes/ingestion_routes.py` / `playbook_draft.py` | 传入 `complete_fact_gate` |
| `tests/test_playbook_fact_gate.py` | 改为 mock Agent + schema 校验用例；陷阱 `trap_check` 测试保留 |
| `tests/test_playbook_drafts.py` / `test_media_pipeline_playbook.py` | 注入 mock `complete_fact_gate` |

---

## 9. 与 `trap_check` 的边界

| 能力 | 用途 | 实现 |
|------|------|------|
| **Draft 过闸** | 打法稿能否选用 / 是否 `fact_gate_fallback` | **仅 Agent**（本 spec） |
| **陷阱题** | 发布打法版本、`auto_uses_current_playbook` 前自检 | **保留** `trap_check` 规则（10 倍、全面超越） |

理由：陷阱题是 **产品固定红线**，与「素材事实核对」不同；若未来也要 Agent 化，另开 spec，不与本闸门混用。

---

## 10. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Agent 误放（幻觉过闸） | fail-closed on error；战报仍只信 `playbook` 归因；运营可抽检；P2 可加「双人模型」或抽检队列 |
| Agent 误杀 | 比规则少；summary 可解释；可人工改稿走 `edited` |
| 延迟与成本 | 独立小模型；与 ranking 并行不可行（依赖稿文），仅串行 |
| 非确定性 | 同稿重跑可能不同；Accept；缓存 **不做**（稿每次新生成） |

---

## 11. 测试策略

1. **单元**：`validate_fact_gate_response` 边界；`fact_gate_summary` 中英文。  
2. **集成**：mock `complete_fact_gate` 返回 pass/fail；`draft_selectable`、`media_pipeline` fallback 字段。  
3. **可选黄金集**（P1）：10 条 `(source, draft, expected_passed)` 仅用于 mock 回归，不跑真模型 CI。

---

## 12. 文档与版本

- 更新 `2026-09-22-playbook-loop-design.md` §7 事实闸门描述为 Agent + checklist。  
- 更新 `2026-09-23-playbook-pattern-ranking-design.md` G2 为「三次模型调用：rank + write + fact_gate_agent」。  
- 本文件批准后由 `writing-plans` 拆任务。

---

## 附录 A：方案对比（已选 Agent-only）

| 方案 | 说明 | 结论 |
|------|------|------|
| A. 纯规则（现状） | 字面数字 | 误杀高 — **弃用** |
| B. 规则 + Agent | 规则先筛 | 用户要求不用规则 — **不采用** |
| C. **纯 Agent（本 spec）** | 单次结构化审核 | **采用** |
| D. Agent 改稿再审 | 失败自动删句 | 复杂度高 — P2 |

---

## 附录 B：自检

- [x] 与 `fact_gate_fallback` / stamp / 战报一致  
- [x] 测试可 mock，无真模型 CI 依赖  
- [x] `trap_check` 边界清晰  
- [ ] 产品确认：低置信 `passed=true` 是否接受（默认接受）
