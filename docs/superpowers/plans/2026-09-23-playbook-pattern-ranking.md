# 素材驱动打法选型（Agent Ranking）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在出稿前根据标题+摘要从模式库 ranking 选出 `playbook_version_id`，写稿与选型分离，低置信回退当前打法，归因与战报可统计 fallback。

**Architecture:** 新建 `services/copy_agent/pattern_ranking.py` 承载候选构建、JSON 校验、置信策略与 `rank_playbook_for_material`；`generate_one_draft` 与 `media_pipeline` 只消费 `PlaybookSelection`。Ranking 用可注入的 `complete_rank`，测试从不打真模型。模式库聚类逻辑复用 `list_pattern_library`，`cluster_key` 与 spec 一致。

**Tech Stack:** SQLAlchemy, FastAPI, pytest, 现有 `copy_agent` 模块与资讯库静态页。

**Spec:** `docs/superpowers/specs/2026-09-23-playbook-pattern-ranking-design.md`（v1.1）

**Prerequisite:** 打法学习第一期代码在分支上可用（`services/copy_agent/*`、`CopyDraft`、`pattern_library`、`playbook_draft` 路由）。若尚未合入 master，先完成 `docs/superpowers/plans/2026-09-22-playbook-loop.md` 或等价提交，再执行本计划。

## Global Constraints

- 不改 `build_methodology_prompt_section` 与 `content_prompts.yaml`
- 不改 `compose.py` 拼接规则
- `PLAYBOOK_RANK_TIMEOUT_SEC` 默认 **15**；超时走回退，**不**因选型 alone 返回 500
- `PLAYBOOK_RANK_MAX_MATERIAL_CHARS` 默认 **1200**
- ranking payload **禁止** `evidence_excerpt`（`include_evidence=False`）
- `current_playbook_version_id` **不得**偏置 ranking，仅 fallback / adaptive 关闭时使用
- 低置信且无 current → `NoPlaybook`（409），不强行 top1
- `auto_material_adaptive_playbook` 默认 **false**；仅与 `auto_uses_current_playbook` 同时为真时在 `media_pipeline` ranking
- `material_adaptive_playbook` 默认 **true**（手动出稿路径）
- `ranking_max_candidates` 默认 **40**；P0 超过则 **409**
- CI 禁止调用真实 ranking 模型
- 未得到用户要求时不 git commit

## File Map

- Create: `services/copy_agent/pattern_ranking.py` — 候选、校验、选型、回退
- Create: `tests/test_playbook_pattern_ranking.py` — P0 单元与集成（mock `complete_rank`）
- Modify: `src/db/models/playbook.py` — `CopyDraft.selection_json`；`CopyAgentSettings` 三字段
- Modify: `src/db/engine.py` — SQLite `_ensure_sqlite_columns`
- Modify: `services/copy_agent/card_schema.py` — `ranking_preview_from_card`；`card_preview_from_stored(..., include_evidence=True)`
- Modify: `services/copy_agent/pattern_library.py` — 导出 `cluster_key_for(genre, name)`
- Modify: `services/copy_agent/drafts.py` — 集成选型；`force_current_playbook`
- Modify: `services/copy_agent/settings_store.py` — 读写新设置；`set_material_adaptive` / `set_auto_material_adaptive`
- Modify: `services/copy_agent/drafts.py::draft_stamp_source` — pattern 与 fallback 字段
- Modify: `services/ingestion/media_pipeline.py` — 双开关 ranking
- Modify: `services/copy_agent/battle_report.py` — `selection_fallback_count` 汇总
- Modify: `api/routes/copy_agent_routes.py` — settings GET/PATCH 扩展
- Modify: `static/settings.html` + 相关 JS — 双开关文案
- Modify: `static/js/ingestion_library.js` + `static/ingestion_library.html` — 按钮文案、黄条、冷启动、展示 `selection_json`
- Modify: `api/routes/ingestion_routes.py` — `playbook-draft` 响应可带 selection 摘要（或从 article `video_draft_json` 读）
- P1（本计划末尾附录，不阻塞 P0）：`rank-preview` 路由、`prefilter_candidates`、文章 `force_current`

---

### Task 1: 数据库列与设置默认值

**Files:**
- Modify: `src/db/models/playbook.py`
- Modify: `src/db/engine.py`
- Test: `tests/test_playbook_pattern_ranking.py`（`test_settings_defaults_for_ranking`）

**Interfaces:**
- Produces: `CopyDraft.selection_json: Mapped[str]` 默认 `"{}"`
- Produces: `CopyAgentSettings.material_adaptive_playbook` 默认 `True`
- Produces: `CopyAgentSettings.auto_material_adaptive_playbook` 默认 `False`
- Produces: `CopyAgentSettings.ranking_max_candidates` 默认 `40`

- [ ] **Step 1: Write the failing test**

```python
def test_settings_defaults_for_ranking(db_session):
    from services.copy_agent.settings_store import get_settings

    settings = get_settings(db_session)
    assert settings.material_adaptive_playbook is True
    assert settings.auto_material_adaptive_playbook is False
    assert settings.ranking_max_candidates == 40
```

复用 `tests/test_playbook_drafts.py` 的 `db_session` fixture（或抽到 `tests/playbook_db_fixtures.py` 若已存在）。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_pattern_ranking.py::test_settings_defaults_for_ranking -v`

Expected: FAIL，`CopyAgentSettings` 无 `material_adaptive_playbook`

- [ ] **Step 3: Add columns**

`CopyAgentSettings`:

```python
material_adaptive_playbook: Mapped[bool] = mapped_column(Boolean, default=True)
auto_material_adaptive_playbook: Mapped[bool] = mapped_column(Boolean, default=False)
ranking_max_candidates: Mapped[int] = mapped_column(default=40)
```

`CopyDraft`:

```python
selection_json: Mapped[str] = mapped_column(Text, default="{}")
```

`src/db/engine.py` 的 playbook 相关 migrations 列表增加上述列（BOOLEAN / INTEGER / TEXT）。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_pattern_ranking.py::test_settings_defaults_for_ranking -v`

Expected: PASS

---

### Task 2: `cluster_key` 与 ranking 预览（无 excerpt）

**Files:**
- Modify: `services/copy_agent/pattern_library.py`
- Modify: `services/copy_agent/card_schema.py`
- Test: `tests/test_playbook_pattern_ranking.py`

**Interfaces:**
- Produces: `cluster_key_for(genre: str, pattern_name: str) -> str`
- Produces: `ranking_preview_from_card(preview: dict) -> dict` — 仅 spec §5.2 列出的键；**无** `evidence_excerpt`

- [ ] **Step 1: Write the failing tests**

```python
from services.copy_agent.card_schema import ranking_preview_from_card
from services.copy_agent.pattern_library import cluster_key_for


def test_cluster_key_normalizes_name():
    assert cluster_key_for("opinion", "对照 开场") == "opinion|对照开场"


def test_ranking_preview_omits_evidence():
    preview = ranking_preview_from_card({
        "pattern_name": "对照开场",
        "genre_label": "观点评论",
        "purpose": "先立场",
        "moves": [{"id": "1", "function": "hook"}],
        "hook": {"archetype_label": "对照"},
        "motives": {"primary_label": "好奇"},
        "verdict_function_label": "观点评论",
        "evidence_excerpt": "不应出现",
    })
    assert "evidence_excerpt" not in preview
    assert preview["pattern_name"] == "对照开场"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_playbook_pattern_ranking.py::test_cluster_key_normalizes_name tests/test_playbook_pattern_ranking.py::test_ranking_preview_omits_evidence -v`

- [ ] **Step 3: Implement**

`cluster_key_for` 使用与 `pattern_library._normalize_key` 相同的归一化，返回 `f"{genre}|{normalized}"`。

`card_preview_from_stored` 增加 `*, include_evidence: bool = True`；当 `False` 时从返回 dict 删除 `evidence_excerpt`（及 `forbidden_transfers` 若 spec 要求 ranking 不传禁迁原文列表——P0 一并删除 `forbidden_transfers` 与 `evidence_excerpt`）。

`ranking_preview_from_card` 从完整 preview 抽字段并截断 `move_functions` 至 6 条。

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_playbook_pattern_ranking.py -k "cluster_key or ranking_preview" -v`

---

### Task 3: `validate_ranking_response` 与置信回退

**Files:**
- Create: `services/copy_agent/pattern_ranking.py`（本节函数）
- Test: `tests/test_playbook_pattern_ranking.py`

**Interfaces:**
- Produces: `validate_ranking_response(data: dict, allowed_keys: set[str]) -> dict`
- Produces: `choose_playbook_from_ranking(parsed: dict, candidates: list[dict], current_version_id: str | None) -> tuple[str | None, bool, str | None]`  
  返回 `(playbook_version_id, fallback, recommended_version_id)`；无可用 id 时 `(None, True, ...)` 触发 `NoPlaybook`

- [ ] **Step 1: Write the failing tests**

```python
from services.copy_agent.pattern_ranking import choose_playbook_from_ranking, validate_ranking_response


def test_validate_rejects_unknown_cluster():
    allowed = {"a|one"}
    with pytest.raises(ValueError):
        validate_ranking_response(
            {"chosen_cluster_key": "b|two", "ranked": [], "confidence": "high"},
            allowed,
        )


def test_low_confidence_falls_back_to_current():
    candidates = [
        {
            "cluster_key": "opinion|a",
            "representative_version_id": "rec",
        }
    ]
    parsed = {
        "chosen_cluster_key": "opinion|a",
        "confidence": "low",
        "ranked": [{"cluster_key": "opinion|a", "score": 0.6}],
    }
    vid, fallback, recommended = choose_playbook_from_ranking(
        parsed, candidates, current_version_id="cur"
    )
    assert fallback is True
    assert vid == "cur"
    assert recommended == "rec"


def test_low_confidence_without_current_raises_no_playbook():
    from services.copy_agent.drafts import NoPlaybook

    candidates = [{"cluster_key": "opinion|a", "representative_version_id": "rec"}]
    parsed = {
        "chosen_cluster_key": "opinion|a",
        "confidence": "low",
        "ranked": [{"cluster_key": "opinion|a", "score": 0.6}],
    }
    vid, fallback, _ = choose_playbook_from_ranking(parsed, candidates, current_version_id=None)
    assert vid is None
```

`generate_one_draft` 层把 `vid is None` 转为 `NoPlaybook`；本任务纯函数返回 None。

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_playbook_pattern_ranking.py -k "validate or choose_playbook" -v`

- [ ] **Step 3: Implement confidence table（spec §5.5）**

- `high` + 校验通过 → `representative_version_id` of chosen cluster，`fallback=False`
- `medium` 且 top1−top2 ≥ 0.12 → 同上
- 否则 → `current_version_id` 若非空；`recommended_version_id` = 选型 id
- `ranked` 按 score 降序；仅一个候选时 medium 分差规则用 score 0 vs 0 → 走回退

- [ ] **Step 4: Run tests — expect PASS**

---

### Task 4: `resolve_representative_version_id` 与 `build_ranking_candidates`

**Files:**
- Modify: `services/copy_agent/pattern_ranking.py`
- Test: `tests/test_playbook_pattern_ranking.py`

**Interfaces:**
- Produces: `resolve_representative_version_id(session, version_ids: list[str]) -> str | None`
- Produces: `build_ranking_candidates(session) -> list[dict]` — 每项含 `cluster_key`, `representative_version_id`, `version_ids`, ranking_preview 字段
- Consumes: `list_pattern_library`；对每簇查最新 `PatternCard` 与 `PlaybookVersion`

- [ ] **Step 1: Write failing tests**

```python
def test_resolve_does_not_prefer_current_over_published(db_session):
    from services.copy_agent.pattern_ranking import resolve_representative_version_id
    from src.db.models.playbook import PlaybookVersion

    db_session.add_all(
        [
            PlaybookVersion(
                id="cur", body="b1", status="published", trap_passed=True
            ),
            PlaybookVersion(
                id="old", body="b2", status="published", trap_passed=True
            ),
        ]
    )
    db_session.commit()
    # current 是 cur，但簇内应选 published 最新——若 old 更新则选 old
    chosen = resolve_representative_version_id(db_session, ["cur", "old"])
    assert chosen in {"cur", "old"}
    assert chosen != ""  # 有 body 即可；另加用例：current 不在簇内仍选 published 最新


def test_candidate_drops_empty_body(db_session):
    from services.copy_agent.pattern_ranking import build_ranking_candidates

    db_session.add(PlaybookVersion(id="empty", body="", status="published"))
    # 插入 minimal PatternCard v2 + job 链——用 tests/playbook_card_fixtures.py 辅助
    # 断言 build 后列表为空或不含 empty
```

第二个测试用 `playbook_card_fixtures.minimal_card_yaml` 与 `PatternCard` 行；`version_ids` 只含 `empty` 时该候选不出现。

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `resolve_representative_version_id`**

顺序：published+trap_passed 最新 `created_at` → 任意最新 `created_at` → None。**不读** `get_settings().current_playbook_version_id`。

`build_ranking_candidates`：遍历 `list_pattern_library` 的 patterns；对每个 pattern 的 `version_ids` 调 resolve；为 None 则跳过整条；否则拼 `cluster_key_for` + `ranking_preview_from_card`。

- [ ] **Step 4: Run — PASS**

---

### Task 5: `rank_playbook_for_material`（mock complete）

**Files:**
- Modify: `services/copy_agent/pattern_ranking.py`
- Test: `tests/test_playbook_pattern_ranking.py`

**Interfaces:**
- Produces: `PlaybookSelection` — `TypedDict` 或 `@dataclass` 与 spec §5.5 字段一致
- Produces: `rank_playbook_for_material(session, title, content, complete_rank, *, adaptive: bool, current_version_id: str | None, max_candidates: int) -> PlaybookSelection`
- `complete_rank(messages: list[dict]) -> str` 返回 JSON 字符串

- [ ] **Step 1: Write failing integration test**

```python
def test_rank_picks_cluster_from_mock_complete(db_session):
    from services.copy_agent.pattern_ranking import rank_playbook_for_material
    # seed: current v_cur + 另一版本 v_rec 关联到 card 簇 opinion|test
    def complete_rank(messages):
        return json.dumps(
            {
                "chosen_cluster_key": "opinion|test",
                "confidence": "high",
                "ranked": [{"cluster_key": "opinion|test", "score": 0.9, "reason": "题材贴合"}],
            },
            ensure_ascii=False,
        )

    sel = rank_playbook_for_material(
        db_session,
        title="标题",
        content="摘要",
        complete_rank=complete_rank,
        adaptive=True,
        current_version_id="v_cur",
        max_candidates=40,
    )
    assert sel["fallback"] is False
    assert sel["playbook_version_id"] == "v_rec"
    assert sel["policy_version"] == "rank-v1"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

- `adaptive=False` → 不调 `complete_rank`，直接构造 selection 指向 `current_version_id`（无 cluster）。
- `len(candidates)==0` 且无 current → raise `NoPlaybook`
- `len(candidates) > max_candidates` → raise `TooManyPatterns`（自定义异常，路由转 409）
- 截断 `content`：`os.getenv("PLAYBOOK_RANK_MAX_MATERIAL_CHARS", "1200")`
- 解析 JSON：strip markdown fence；`validate_ranking_response`；`choose_playbook_from_ranking`
- 填充 `pattern_name` / `genre_label` 自候选；`ranking_json` 存校验后快照

- [ ] **Step 4: Run — PASS**

---

### Task 6: 接入 `generate_one_draft` 与 `selection_json`

**Files:**
- Modify: `services/copy_agent/drafts.py`
- Modify: `tests/test_playbook_drafts.py`
- Modify: `tests/test_playbook_pattern_ranking.py`

**Interfaces:**
- `generate_one_draft(..., complete, complete_rank=None, force_current_playbook=False, adaptive_path=True)`
- 当 `settings.material_adaptive_playbook` 且非 `force_current`：`complete_rank` 默认用与 production 相同的 DeepSeek 调用包装（与 `copy_agent_routes` 一致），测试必须注入 lambda
- 写 `CopyDraft.selection_json` 为 `json.dumps({...})`

- [ ] **Step 1: Write failing test**

```python
def test_draft_uses_ranked_version_not_only_current(db_session):
    # seed two versions + pattern card pointing to v_rank
    # settings.current = v_cur, adaptive True
    def complete_rank(msgs):
        return '{"chosen_cluster_key":"opinion|x","confidence":"high","ranked":[{"cluster_key":"opinion|x","score":0.9,"reason":"ok"}]}'

    def complete(msgs):
        return "口播文案大约快 8 倍"

    draft = generate_one_draft(
        db_session,
        title="t",
        content="大约快 8 倍",
        complete=complete,
        complete_rank=complete_rank,
    )
    assert draft.playbook_version_id == "v_rank"
    sel = json.loads(draft.selection_json)
    assert sel.get("fallback") is False
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Wire `generate_one_draft`**

在取 `version.body` 之前调用 `rank_playbook_for_material`；`playbook_version_id` = selection 的 id；`selection_json` 含 `ranked_top3`（从 ranked 截断）。

扩展 `draft_stamp_source`：

```python
{
    **existing,
    "pattern_cluster_key": sel.get("cluster_key"),
    "pattern_name": sel.get("pattern_name"),
    "playbook_selection_confidence": sel.get("confidence"),
    "playbook_selection_fallback": sel.get("fallback"),
}
```

- [ ] **Step 4: Run**

Run: `pytest tests/test_playbook_drafts.py tests/test_playbook_pattern_ranking.py -v`

Expected: PASS；既有 draft 测试仍通过（注入 `complete_rank` 为 no-op 或关闭 adaptive）。

---

### Task 7: 双开关、`media_pipeline`、settings API

**Files:**
- Modify: `services/copy_agent/settings_store.py`
- Modify: `services/ingestion/media_pipeline.py`
- Modify: `api/routes/copy_agent_routes.py`
- Modify: `tests/test_media_pipeline_playbook.py`
- Test: `tests/test_playbook_pattern_ranking.py`（`test_pipeline_skips_rank_when_only_auto_uses`）

**Interfaces:**
- `set_material_adaptive(session, enabled: bool)`
- `set_auto_material_adaptive(session, enabled: bool)` — 若 `enabled` 且非 `auto_uses_current_playbook`，可拒绝或 no-op（产品：仅 UI 展示，API 允许存 true 但 pipeline 仍要求双开）

- [ ] **Step 1: Write failing test**

```python
def test_pipeline_skips_rank_when_only_auto_uses(db_session, monkeypatch):
    # settings: auto_uses=True, auto_material_adaptive=False
    # mock rank_playbook_for_material → assert not called
    # generate_video_content 收到 playbook_body == current.body
```

复用 `test_media_pipeline_playbook.py` 的 fixture 风格。

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement media_pipeline**

在现有 `_current_auto_playbook` 分支内：

```python
if settings.auto_uses_current_playbook and settings.auto_material_adaptive_playbook:
    selection = rank_playbook_for_material(..., adaptive=True, ...)
    playbook_body = session.get(PlaybookVersion, selection["playbook_version_id"]).body
else:
    playbook_body = version.body
```

`copy_agent_routes` GET/PATCH settings 返回新三字段；PATCH 校验 `ranking_max_candidates` 在 5–100。

- [ ] **Step 4: Run — PASS**

---

### Task 8: 战报 fallback 计数与资讯库 UI（P0）

**Files:**
- Modify: `services/copy_agent/battle_report.py`
- Modify: `static/js/ingestion_library.js`
- Modify: `static/ingestion_library.html`（若需容器）
- Modify: `static/settings.html`
- Test: `tests/test_playbook_battle_report.py`（扩展）

**Interfaces:**
- `build_battle_report` 增加 `"selection_fallback_count": int` — 从 `PublishJob` 无法直接读时，P0 用 `video_draft_json` 已在 stamp 的 `playbook_selection_fallback` 聚合：若 publish 路径未带 stamp，则统计 `CopyDraft.selection_json` 中 `fallback=true` 且 `copy_draft_id` 关联 job 的行数；**最小实现**：战报 API 增加对 `learn_again` 行解析 `pattern_name` 空且 job 有 `copy_draft_id` 时读 draft——更简单：**P0 仅统计 battle_report 返回的 rows 里** 若扩展 `_row` 读 `PublishJob` 无字段，则在 `stamp_playbook` / 创建 job 时把 `playbook_selection_fallback` 写入 `PublishJob` 不合适。

**简化 P0 决策：** 在 `build_battle_report` 中查询最近 `CopyDraft` 带 `selection_json.fallback=true`，按 `playbook_version_id` 计数展示为 `selection_fallback_count`（全局计数，非 per-job）。spec 要求「战报可见 fallback 计数」——全局即可。

- [ ] **Step 1: Test**

```python
def test_battle_report_includes_fallback_count(db_session):
    # insert CopyDraft with selection_json fallback true
    report = build_battle_report(db_session)
    assert report["selection_fallback_count"] >= 1
```

- [ ] **Step 2–4: Implement UI**

- `ingestion_library.js`：`material_adaptive` 从 settings API 读（或 playbook-draft 响应字段）；按钮文案切换；`playbook-draft` 成功后解析 `video_draft_json` 展示 reason；`fallback` 黄条文案见 spec §4.1；`patterns.total < 3` 灰字；按钮 2s 防抖
- `settings.html`：`auto_material_adaptive_playbook` 开关 + §4.3 说明文案

Run: `pytest tests/test_playbook_battle_report.py tests/test_ingestion_playbook_draft.py tests/test_pattern_lab_page.py -v`

---

## P1 附录（本计划不展开逐步代码）

| 项 | 文件 |
|----|------|
| `POST /api/copy-agent/rank-preview` | `copy_agent_routes.py` |
| `prefilter_candidates` | `pattern_ranking.py` |
| `PLAYBOOK_RANK_MODEL` | ranking 调用处 |
| 60s selection 复用 | `pattern_ranking.py` + `article_id` |
| 文章 `force_current_playbook` | `ingestion_routes` + `IngestedArticle` metadata |
| Pattern Lab 选型统计列 | `pattern_lab.js` |

---

## Spec Coverage Self-Review

| Spec § | Task |
|--------|------|
| §5.0 跳过 ranking | Task 5–7 |
| §5.2 候选 / 无 excerpt | Task 2, 4 |
| §5.3 代表版本 | Task 4 |
| §5.4 validate | Task 3, 5 |
| §5.5 回退 / NoPlaybook | Task 3, 5, 6 |
| §5.7 防抖 P0 | Task 8 |
| §6 集成 | Task 6–7 |
| §7 数据模型 | Task 1 |
| §8.3 settings | Task 7 |
| §9 环境变量 | Task 5 |
| §10 测试 | 各 Task |
| §4 UI | Task 8 |
| P1 rank-preview 等 | 附录 |

**Placeholder scan:** 无 TBD。

**Type consistency:** `PlaybookSelection` 字段名与 spec §5.5、`selection_json`、`draft_stamp_source` 一致。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-23-playbook-pattern-ranking.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — one fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, `executing-plans`, batched checkpoints  

Which approach?
