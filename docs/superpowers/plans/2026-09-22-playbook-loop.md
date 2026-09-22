# 打法学习第一期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 贴屏幕文案经 `dsh` 拆成当前打法，主页按它出一稿；自动出片默认仍走宪法，打开开关后才用当前打法，闸门失败可见且不计入成绩。

**Architecture:** 打法存在 `playbook_versions`，不写入 `build_methodology_prompt_section`。归因用 `PublishJob.playbook_attribution` 三列一起盖戳。`dsh` 只在拆卡沙箱里跑，路径审计失败则不入库。主页旧生成与自动出片在开关关闭时的消息保持今天的两份快照。

**Tech Stack:** SQLAlchemy, FastAPI, pytest, 现有静态页与 `app_nav.js`。DeepSeek Harness 仅第一期拆卡子进程，测试用假 runner。

**Spec:** `docs/superpowers/specs/2026-09-22-playbook-loop-design.md`（v3）

## Global Constraints

- 不改 `should_run_media_pipeline` 的等级与分数，不改 `auto_publish.min_grade`
- 不改 `content_prompts.yaml` 正文，不改 `build_methodology_prompt_section` 函数体
- `/api/generate-summary` 不接受打法参数，不读打法表
- `generate_video_content(..., playbook_body=None)` 的消息与今天一致
- 宪法版归因是 `NULL`，禁止写入字符串 `constitution`
- 升降与「再学」只统计 `playbook_attribution='playbook'`
- 同用户可读盘是接受的残余风险；路径审计只丢弃脏入库
- 第一期 N=1；不做三稿、不做满 8 条门槛、不做两个独立版本指针
- 第一期不接 GitHub 视频制作，不把 `dsh` 打进 Tauri
- 未得到用户要求时不 git commit

## File Map

- Create: `src/db/models/playbook.py` — 打法、模式卡、任务、稿、设置
- Create: `services/publishing/playbook_stamp.py` — `stamp_playbook`
- Create: `services/copy_agent/fact_gate.py` — 事实闸门与陷阱检查
- Create: `services/copy_agent/compose.py` — 宪法在 system、打法附在 user
- Create: `services/copy_agent/settings_store.py` — 当前版本与自动开关
- Create: `services/copy_agent/audit.py` — 路径审计与环境变量白名单
- Create: `services/copy_agent/curate.py` — 假 runner 可替换的拆卡
- Create: `services/copy_agent/drafts.py` — 一稿出稿
- Create: `services/copy_agent/battle_report.py` — 战报聚合
- Create: `api/routes/copy_agent_routes.py`
- Create: `static/pattern_lab.html`, `static/js/pattern_lab.js`
- Create: `tests/test_playbook_stamp.py`, `tests/test_playbook_fact_gate.py`, `tests/test_playbook_compose.py`, `tests/test_playbook_curate.py`, `tests/test_playbook_drafts.py`, `tests/test_playbook_battle_report.py`, `tests/test_playbook_api.py`
- Modify: `src/db/engine.py` — import 新模型；`publish_jobs` 加三列
- Modify: `src/db/models/publishing.py` — 三列 ORM
- Modify: `services/publishing/auto_publish.py::create_ingestion_publish_job`
- Modify: `services/publishing/platform_jobs.py::_create_job_for_platform`
- Modify: `api/routes/publishing_routes.py` 创建任务处
- Modify: `api/schemas/publishing_models.py::CreatePublishJobRequest`
- Modify: `services/content_generation_service.py::generate_video_content` — 仅增加可选 `playbook_body`
- Modify: `services/ingestion/media_pipeline.py` — 第 7 节状态机
- Modify: `api/routes/ingestion_routes.py` — `rerender-playbook`
- Modify: `api/routes/main_routes.py` — `/pattern-lab`
- Modify: `web_server.py` — 注册路由
- Modify: `static/js/shared/app_nav.js`, `static/index.html`, `static/js/index/main.js`, `static/settings.html`

---

### Task 1: 表与 PublishJob 三列

**Files:**
- Create: `src/db/models/playbook.py`
- Modify: `src/db/models/publishing.py`（`PublishJob` 三列）
- Modify: `src/db/engine.py`（`init_db` import；`_ensure_sqlite_columns` 的 `pub_migrations`）
- Test: `tests/test_playbook_stamp.py`（本任务只断言表与空列插入）

**Interfaces:**
- Produces: `PlaybookVersion`, `PatternCard`, `CopyAgentJob`, `CopyDraft`, `CopyAgentSettings`
- Produces: `PublishJob.playbook_version_id`, `copy_draft_id`, `playbook_attribution` 均可空

- [ ] **Step 1: Write the failing test**

```python
def test_publish_job_inserts_with_null_playbook_columns(db_session):
    job = PublishJob(
        account_id="acc",
        video_path="data/videos/a.mp4",
        title="标题",
    )
    db_session.add(job)
    db_session.commit()
    assert job.playbook_version_id is None
    assert job.copy_draft_id is None
    assert job.playbook_attribution is None
```

用 `tests/test_publishing_auto_publish.py` 里的 `db_session` fixture 写法：`INGESTION_DATABASE_URL` 指向 `tmp_path`，调用 `init_db()`。账号外键若插入失败，先插一条 `PublisherAccount`。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_stamp.py::test_publish_job_inserts_with_null_playbook_columns -v`

Expected: FAIL，`PublishJob` 没有 `playbook_version_id`

- [ ] **Step 3: Add models and columns**

`PublishJob` 增加：

```python
playbook_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
copy_draft_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
playbook_attribution: Mapped[str | None] = mapped_column(String(32), nullable=True)
```

`src/db/engine.py` 的 `pub_migrations` 增加这三列，类型 `VARCHAR(32)`。`init_db` 增加 `import src.db.models.playbook`。

`playbook.py` 用现有 `_uuid` 风格。`CopyAgentSettings` 只有一行可预期的用法：`id="default"`，`current_playbook_version_id` 可空，`auto_uses_current_playbook` 默认 `False`。`PlaybookVersion.status` 用字符串，不建数据库枚举。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_stamp.py::test_publish_job_inserts_with_null_playbook_columns tests/test_publishing_auto_publish.py -v`

Expected: PASS。现有自动发布测试仍通过。

---

### Task 2: stamp_playbook

**Files:**
- Create: `services/publishing/playbook_stamp.py`
- Modify: `services/publishing/auto_publish.py`（`create_ingestion_publish_job` 在 `session.add` 前）
- Modify: `services/publishing/platform_jobs.py`（`_create_job_for_platform` 在 `session.add` 前）
- Modify: `api/routes/publishing_routes.py`（约第 297 行 `PublishJob(...)` 之后、`db.add` 之前）
- Modify: `api/schemas/publishing_models.py::CreatePublishJobRequest`
- Test: `tests/test_playbook_stamp.py`

**Interfaces:**
- Consumes: `PublishJob` 三列
- Produces: `stamp_playbook(job, source: dict | None) -> None`
- `source` 键：`playbook_version_id`, `copy_draft_id`, `playbook_attribution`

合法组合只有规格第 8 节那张表。其他组合抛 `ValueError`。`source is None` 或三键都缺：三列保持 `None`。

- [ ] **Step 1: Write the failing tests**

```python
def test_stamp_playbook_keeps_edited_version():
    job = PublishJob(account_id="a", video_path="v.mp4", title="t")
    stamp_playbook(job, {
        "playbook_attribution": "edited",
        "playbook_version_id": "ver1",
        "copy_draft_id": "draft1",
    })
    assert job.playbook_attribution == "edited"
    assert job.playbook_version_id == "ver1"
    assert job.copy_draft_id == "draft1"


def test_stamp_rejects_constitution_string():
    job = PublishJob(account_id="a", video_path="v.mp4", title="t")
    with pytest.raises(ValueError):
        stamp_playbook(job, {"playbook_version_id": "constitution"})


def test_stamp_fact_gate_fallback_has_null_version():
    job = PublishJob(account_id="a", video_path="v.mp4", title="t")
    stamp_playbook(job, {"playbook_attribution": "fact_gate_fallback"})
    assert job.playbook_version_id is None
    assert job.copy_draft_id is None
```

再加一条：`playbook` 缺 `copy_draft_id` 时抛 `ValueError`。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_stamp.py -v`

Expected: FAIL，`stamp_playbook` 未定义

- [ ] **Step 3: Implement stamp and call it at three sites**

```python
_PLAYBOOK = {"playbook"}
_FALLBACK = {"fact_gate_fallback", "generation_fallback"}


def stamp_playbook(job, source: dict | None) -> None:
    source = source or {}
    if source.get("playbook_version_id") == "constitution":
        raise ValueError("constitution is not a playbook id")
    attr = source.get("playbook_attribution") or None
    version = source.get("playbook_version_id") or None
    draft = source.get("copy_draft_id") or None
    if attr is None and version is None and draft is None:
        return
    if attr == "playbook" or attr == "edited":
        if not version or not draft:
            raise ValueError("playbook attribution requires version and draft")
    elif attr in _FALLBACK:
        version = None
        draft = None
    else:
        raise ValueError(f"invalid playbook attribution: {attr}")
    job.playbook_attribution = attr
    job.playbook_version_id = version
    job.copy_draft_id = draft
```

`create_ingestion_publish_job` 与 `_create_job_for_platform`：从文章 `video_draft_json` 解析 dict 后调用。`publishing_routes`：请求体字段优先；缺省且 `source_id` 能载到 `IngestedArticle` 时用文章草稿。`orchestrator.py` 的 `probe_job` 不调用。

`CreatePublishJobRequest` 增加三个可选字段，类型 `Optional[str] = None`。

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_playbook_stamp.py tests/test_publishing_auto_publish.py -v`

Expected: PASS

---

### Task 3: 事实闸门与陷阱检查

**Files:**
- Create: `services/copy_agent/fact_gate.py`
- Test: `tests/test_playbook_fact_gate.py`

**Interfaces:**
- Produces: `fact_gate(draft_text: str, source_text: str) -> dict`，形如 `{"passed": bool, "violations": list[str]}`
- Produces: `trap_check(draft_text: str) -> dict`，形如 `{"passed": bool, "failures": list[str]}`

陷阱题固定原文含义：约 8 倍不得写成 10 倍；无评测不得出现「全面超越」。实现时用草稿文本本身判定，不调用模型。`10倍`、`10 倍`、`全面超越` 出现即失败。数字必须在 `source_text` 中作为连续子串出现；草稿里有而原文没有的「倍」比较记入 `violations`。

- [ ] **Step 1: Write the failing tests**

```python
def test_trap_rejects_ten_x_and_universal_win():
    assert trap_check("快 10 倍，多项评测全面超越")["passed"] is False


def test_trap_allows_eight_x():
    assert trap_check("大约快 8 倍，可本地部署")["passed"] is True


def test_fact_gate_rejects_number_missing_from_source():
    result = fact_gate("耗时 3 年，3 天被追上", "社区用了很短时间做出对标实现")
    assert result["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_fact_gate.py -v`

Expected: FAIL

- [ ] **Step 3: Implement the two functions**

数字用正则抽出草稿中的整数与小数。每个数字去掉空白后必须在 `source_text` 里出现。`全面超越` 只要草稿含有且 `source_text` 不含，即失败。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_fact_gate.py -v`

Expected: PASS

---

### Task 4: 提示词拼接

**Files:**
- Create: `services/copy_agent/compose.py`
- Modify: `services/content_generation_service.py::generate_video_content` 签名增加 `playbook_body: str | None = None`
- Test: `tests/test_playbook_compose.py`

**Interfaces:**
- Produces: `compose_copy_messages(*, methodology_user: str, playbook_body: str | None, system_role: str) -> list[dict]`

`playbook_body` 为空时，user 内容等于 `methodology_user`。非空时在 user 末尾加 `\n\n【打法】\n` 加正文。system 始终等于传入的 `system_role`。不得修改 `build_methodology_prompt_section`。

`generate_video_content` 在组装 messages 时调用 `compose_copy_messages`。默认 `playbook_body=None`，因此现有自动出片调用点不传该参数时行为不变。

- [ ] **Step 1: Write the failing test**

```python
def test_compose_omits_playbook_when_empty():
    msgs = compose_copy_messages(
        methodology_user="USER", playbook_body=None, system_role="SYS"
    )
    assert msgs[0]["content"] == "SYS"
    assert msgs[1]["content"] == "USER"


def test_compose_appends_playbook_to_user_only():
    msgs = compose_copy_messages(
        methodology_user="USER", playbook_body="对照放前三秒", system_role="SYS"
    )
    assert msgs[0]["content"] == "SYS"
    assert msgs[1]["content"].startswith("USER")
    assert "对照放前三秒" in msgs[1]["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_compose.py -v`

Expected: FAIL

- [ ] **Step 3: Implement compose and thread the optional argument**

不要在 `generate_summary` 里调用 `compose_copy_messages`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_compose.py -v`

Expected: PASS

---

### Task 5: 当前打法与自动开关

**Files:**
- Create: `services/copy_agent/settings_store.py`
- Test: `tests/test_playbook_api.py` 中的存储与发布规则用例（本任务先写存储，不写 HTTP）

**Interfaces:**
- Produces: `get_settings(session) -> CopyAgentSettings`
- Produces: `publish_version(session, version_id: str) -> None`
- Produces: `set_auto_switch(session, enabled: bool) -> None`

`get_settings` 没有行时插入 `id="default"`。

`publish_version`：版本必须已存在。若 `auto_uses_current_playbook` 为真且 `version.trap_passed` 为假，抛 `AutoSwitchBlocksPublish`，消息含「先关掉」。否则把 `current_playbook_version_id` 设为该版本，`status` 改为 `published`。开关状态不变。

`set_auto_switch(True)`：当前版本为空或 `trap_passed` 为假则抛 `TrapCheckFailed`。`False` 总是成功。

- [ ] **Step 1: Write the failing tests**

```python
def test_publish_blocked_when_auto_on_and_trap_failed(db_session):
    settings = get_settings(db_session)
    settings.auto_uses_current_playbook = True
    settings.current_playbook_version_id = "old"
    bad = PlaybookVersion(id="new", body="x", status="candidate", trap_passed=False, parent_id="old")
    db_session.add(bad)
    db_session.commit()
    with pytest.raises(AutoSwitchBlocksPublish) as exc:
        publish_version(db_session, "new")
    assert "先关掉" in str(exc.value)
    assert get_settings(db_session).current_playbook_version_id == "old"
```

```python
def test_publish_allows_trap_failure_when_auto_off(db_session):
    bad = PlaybookVersion(id="new", body="x", status="candidate", trap_passed=False)
    db_session.add(bad)
    db_session.commit()
    publish_version(db_session, "new")
    assert get_settings(db_session).current_playbook_version_id == "new"


def test_auto_switch_rejects_failed_trap(db_session):
    ver = PlaybookVersion(id="v", body="x", status="published", trap_passed=False)
    db_session.add(ver)
    db_session.commit()
    publish_version(db_session, "v")
    with pytest.raises(TrapCheckFailed):
        set_auto_switch(db_session, True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_api.py -v -k "publish_blocked or publish_allows or auto_switch"`

Expected: FAIL

- [ ] **Step 3: Implement the store**

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_api.py -v -k "publish or auto_switch"`

Expected: PASS

---

### Task 6: 路径审计与环境变量白名单

**Files:**
- Create: `services/copy_agent/audit.py`
- Test: `tests/test_playbook_curate.py`

**Interfaces:**
- Produces: `audit_tool_paths(jsonl_text: str, allowed_roots: list[Path]) -> list[str]`，返回越界路径；空列表表示通过
- Produces: `harness_env(base: dict[str, str]) -> dict[str, str]`
- 白名单键：`PATH`, `SYSTEMROOT`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`，再加上调用方传入的 `extra_required: dict[str, str]`

- [ ] **Step 1: Write the failing tests**

```python
def test_audit_rejects_path_outside_workspace(tmp_path):
    workspace = tmp_path / "job"
    workspace.mkdir()
    line = json.dumps({"tool": "bash", "path": "D:/git/AINews/.env"})
    assert audit_tool_paths(line + "\n", [workspace]) == ["D:/git/AINews/.env"]


def test_harness_env_drops_unlisted_secrets():
    env = harness_env({"PATH": "C:\\Windows", "DEEPSEEK_API_KEY": "sk", "AWS_SECRET": "nope"})
    assert "AWS_SECRET" not in env
    assert env["DEEPSEEK_API_KEY"] == "sk"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_curate.py -v -k "audit or harness_env"`

Expected: FAIL

- [ ] **Step 3: Implement audit**

JSONL 每行里递归收集字符串值中含盘符、`/` 或 `\\` 的片段。用 `Path.resolve()` 判断是否位于任一 `allowed_roots` 之下。解析失败的路径视为越界。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_curate.py -v -k "audit or harness_env"`

Expected: PASS

---

### Task 7: 拆卡任务（假 runner）

**Files:**
- Create: `services/copy_agent/curate.py`
- Test: `tests/test_playbook_curate.py`

**Interfaces:**
- Produces: `run_curate(session, *, text: str, runner) -> CopyAgentJob`
- `runner(workspace: Path, session_root: Path, session_id: str, env: dict) -> None`，由 runner 写入 `drafts/card.yaml`、`drafts/playbook.diff.yaml` 和 session JSONL

没有 `text` 则任务 `status=needs_text`，不调用 runner。runner 之后先 `audit_tool_paths`。越界则 `rejected_escape`，不写 `PatternCard` 与 `PlaybookVersion`。`verdict.kind` 不是 `opinion` 则 `rejected_schema`。通过则两张表都写入，版本 `status=candidate`，并按 `trap_check` 写 `trap_passed`。

- [ ] **Step 1: Write the failing test**

```python
def test_curate_discards_yaml_when_tool_path_escapes(db_session, tmp_path, monkeypatch):
    def runner(workspace, session_root, session_id, env):
        (workspace / "drafts").mkdir()
        (workspace / "drafts" / "card.yaml").write_text(
            "verdict:\n  kind: opinion\n  function: 一句判断\n", encoding="utf-8"
        )
        (workspace / "drafts" / "playbook.diff.yaml").write_text("body: 对照\n", encoding="utf-8")
        (session_root).mkdir(parents=True, exist_ok=True)
        (session_root / "session.jsonl").write_text(
            '{"path": "D:/git/AINews/.env"}\n', encoding="utf-8"
        )

    job = run_curate(db_session, text="三年对三天", runner=runner)
    assert job.status == "rejected_escape"
    assert db_session.query(PatternCard).count() == 0
```

再写一条成功路径：JSONL 路径在 workspace 内，`PatternCard` 与 `PlaybookVersion` 各一行，且 diff 正文含「全面超越」时 `trap_passed` 为假。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_curate.py -v -k curate`

Expected: FAIL

- [ ] **Step 3: Implement run_curate**

工作目录用 `tmp_path` 或 `get_data_dir()/copy_agent/workspaces/{job_id}`。测试通过 monkeypatch `get_data_dir`。不要在本任务启动真实 `dsh`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_curate.py -v`

Expected: PASS

---

### Task 8: 学习环 HTTP 与未安装检测

**Files:**
- Create: `api/routes/copy_agent_routes.py`
- Modify: `web_server.py` — `include_router`
- Test: `tests/test_playbook_api.py`

**Interfaces:**
- `GET /api/copy-agent/harness` → `{"ready": bool, "lines": [str, str, str]}`
- `POST /api/copy-agent/materials` JSON `{"text": "..."}` → `{"job_id", "status"}`
- `GET /api/copy-agent/jobs/{id}` → 成功时 `summary="这次只写了草稿目录里的文件。"`；`rejected_escape` 时 `summary="这次写到了草稿目录外面，结果已丢弃。"`
- `POST /api/copy-agent/versions/{id}/publish`
- `POST /api/copy-agent/auto-switch` JSON `{"enabled": bool}`

`ready` 为假时 `lines` 恰好三句，与规格 4.3 一致，且不含「白名单」「JSONL」「ACL」。检测用 `shutil.which("dsh")`。测试 monkeypatch 这个检测函数，不要求本机安装 `dsh`。

发布 409 的 body：`{"message": "...先关掉...", "hint": "disable_auto_switch"}`。

- [ ] **Step 1: Write the failing API tests**

```python
def test_harness_not_ready_copy(client, monkeypatch):
    monkeypatch.setattr("api.routes.copy_agent_routes.dsh_installed", lambda: False)
    body = client.get("/api/copy-agent/harness").json()
    assert body["ready"] is False
    assert len(body["lines"]) == 3
    blob = "".join(body["lines"])
    for word in ("白名单", "JSONL", "ACL"):
        assert word not in blob


def test_publish_http_tells_user_to_disable_switch(client, db_session):
    settings = get_settings(db_session)
    settings.auto_uses_current_playbook = True
    settings.current_playbook_version_id = "old"
    db_session.add(PlaybookVersion(id="new", body="全面超越", status="candidate", trap_passed=False, parent_id="old"))
    db_session.commit()
    res = client.post("/api/copy-agent/versions/new/publish")
    assert res.status_code == 409
    assert res.json()["hint"] == "disable_auto_switch"
    assert "先关掉" in res.json()["message"]
```

`client` fixture：`TestClient` 挂上 `copy_agent_routes.router`，数据库用 Task 1 的 `tmp_path` + `init_db()`。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_api.py -v -k "harness or materials or publish_http"`

Expected: FAIL，404

- [ ] **Step 3: Implement routes**

`materials` 调用 `run_curate`。生产 runner 留一个函数 `start_dsh(workspace, session_root, session_id, env)`，内部 `subprocess` 调用 `dsh`，环境用 `harness_env`。测试注入假 runner 的方式：`run_curate(..., runner=...)`，路由在测试里通过依赖覆盖替换 runner。不要让测试真的拉起 PowerShell。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_api.py -v`

Expected: PASS

---

### Task 9: 主页一稿

**Files:**
- Create: `services/copy_agent/drafts.py`
- Modify: `api/routes/copy_agent_routes.py`
- Test: `tests/test_playbook_drafts.py`

**Interfaces:**
- Produces: `generate_one_draft(session, *, title: str, content: str, complete) -> CopyDraft`
- `complete(messages: list[dict]) -> str` 返回模型正文，测试注入
- `POST /api/copy-agent/drafts`，无当前打法时 409 `no_playbook`，且 `complete` 不被调用
- `POST /api/copy-agent/drafts/{id}/select`
- 选用后若请求 `{"edited": true}`，归因改为 `edited`，版本号保留

事实闸门不通过：稿仍保存，`fact_gate_json.passed` 为假，接口字段 `selectable=false`。

- [ ] **Step 1: Write the failing test**

```python
def test_drafts_do_not_call_model_without_current_playbook(db_session):
    called = {"n": 0}

    def complete(messages):
        called["n"] += 1
        return "口播"

    with pytest.raises(NoPlaybook):
        generate_one_draft(db_session, title="t", content="c", complete=complete)
    assert called["n"] == 0
```

再写：有当前打法且模型返回「快 10 倍」而原文没有 10 时，`selectable` 为假。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_drafts.py -v`

Expected: FAIL

- [ ] **Step 3: Implement generate_one_draft**

用 `compose_copy_messages` 与当前 `PlaybookVersion.body`。不要调用 `/api/generate-summary`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_drafts.py -v`

Expected: PASS

---

### Task 10: 自动出片状态机与重新出片

**Files:**
- Modify: `services/ingestion/media_pipeline.py` 的 `generate_content` 分支
- Modify: `api/routes/ingestion_routes.py` — `POST /api/ingestion/articles/{id}/rerender-playbook`
- Test: `tests/test_playbook_drafts.py` 增加管道用例，或 `tests/test_media_pipeline_playbook.py`

**Interfaces:**
- 开关关：不读打法表，`video_draft_json` 不含 `playbook_attribution`
- 开关开且闸门失败：`playbook_attribution=fact_gate_fallback`，版本号为空，随后仍执行现有渲染与 `maybe_enqueue_auto_publish_jobs` 的条件（本测试可在生成步骤后断言草稿，不必真渲染视频）
- 模型抛错：`playbook_attribution=generation_fallback`
- 重新出片把 `generate_content` 强制为真，并走同一状态机。不要改 `build_manual_media_retry_config`

把「出一稿」抽成 Task 9 的 `generate_one_draft`，管道只负责按开关选择调用它或原来的 `generate_video_content()`。

- [ ] **Step 1: Write the failing test**

构造一篇文章、打开自动开关、当前打法的正文会导致闸门失败。monkeypatch `generate_video_content` 记录调用次数并返回一份无打法草稿。断言调用了两次中的无打法那次，且 `playbook_attribution=="fact_gate_fallback"`。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_media_pipeline_playbook.py -v`

Expected: FAIL

- [ ] **Step 3: Implement the three branches from spec section 7**

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_media_pipeline_playbook.py tests/test_publishing_auto_publish.py -v`

Expected: PASS。开关关闭的现有自动发布行为不变。

---

### Task 11: 战报

**Files:**
- Create: `services/copy_agent/battle_report.py`
- Modify: `api/routes/copy_agent_routes.py` — `GET /api/copy-agent/battle-report`
- Test: `tests/test_playbook_battle_report.py`

**Interfaces:**
- Produces: `build_battle_report(session) -> dict`
- 键：`rows`，每行含 `attribution`, `playbook_version_id`, `platform`, `share_count`, `like_count`, `ratio`（赞为 0 或空时 `ratio` 为 `None`，`ratio_note` 为「无赞，未算比率」）
- 键：`learn_again`，只含 `attribution=="playbook"` 的行

快照取 `PublishPostMetricSnapshot` 中该 `job_id`、`fetched_at` 不晚于 `published_at + 72 小时` 的最近一条。没有快照的任务仍出现在 `rows`，计数字段为空。

- [ ] **Step 1: Write the failing tests**

三条任务：`playbook`、`edited`、`fact_gate_fallback`。赞为 0 的 `playbook` 行 `ratio is None` 且仍在 `rows` 中。`learn_again` 只有 `playbook` 那条。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playbook_battle_report.py -v`

Expected: FAIL

- [ ] **Step 3: Implement the query**

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playbook_battle_report.py -v`

Expected: PASS

---

### Task 12: 打法学习页、导航、主页按钮

**Files:**
- Create: `static/pattern_lab.html`, `static/js/pattern_lab.js`
- Modify: `api/routes/main_routes.py` — `GET /pattern-lab` 返回该 HTML
- Modify: `static/js/shared/app_nav.js` — 「制作」组、视频制作之前：`{ href: '/pattern-lab', label: '打法学习', icon: 'film' }`
- Modify: `static/index.html` — 在「生成AI标题和摘要」与「一键生成视频」之间加按钮 `按当前打法出稿`，默认 `disabled`
- Modify: `static/js/index/main.js` — 无当前打法时保持禁用；有则 `POST /api/copy-agent/drafts`，`selectable` 为真才写入现有输入框
- Modify: `static/settings.html` — 「标题文案」面板顶部一句：「打法版本在打法学习页发布，这里的保存不会写入打法。」

**Interfaces:**
- Consumes: Task 8 与 Task 9 的 API

- [ ] **Step 1: Write a failing UI contract test**

在 `tests/test_ui_p0_redesign.py` 的页面清单旁新增断言，或新建 `tests/test_pattern_lab_page.py`：

```python
def test_pattern_lab_install_copy_has_no_engineer_jargon():
    html = (ROOT / "static" / "pattern_lab.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "pattern_lab.js").read_text(encoding="utf-8")
    blob = html + js
    for word in ("白名单", "JSONL", "ACL", "danger-full-access"):
        assert word not in blob
    assert "重新检测" in js
    assert "先关掉" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pattern_lab_page.py -v`

Expected: FAIL，文件不存在

- [ ] **Step 3: Implement the page**

`pattern_lab.js` 启动时 `GET /api/copy-agent/harness`。`ready=false` 时只渲染 `lines` 三行和「重新检测」，不渲染 textarea。`ready=true` 时显示贴文框。任务成功显示接口返回的 `summary`，路径放在 `<details>` 中。发布按钮调用 publish；若 409 且 `hint=disable_auto_switch`，把 `message` 显示在按钮下。

主页：页面加载时 `GET` 一个只读设置接口。在 Task 8 增加 `GET /api/copy-agent/settings`，返回 `{ "has_current": bool }`。`has_current` 为假则按钮保持 disabled，title 为「先在打法学习贴一条爆款文案」。

资讯库状态行：若文章 `video_draft_json.playbook_attribution` 为 `fact_gate_fallback` 或 `generation_fallback`，在现有成片状态文字后追加规格里的那两句。改 `static/js/ingestion_library.js` 已有的状态渲染，不新建页面。

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_pattern_lab_page.py tests/test_playbook_api.py tests/test_playbook_drafts.py tests/test_media_pipeline_playbook.py tests/test_playbook_battle_report.py tests/test_publishing_auto_publish.py -v`

Expected: PASS

---

## Spec coverage

| 规格 | 任务 |
|---|---|
| 4.2 环境变量与路径审计只防脏入库 | Task 6、Task 7 |
| 4.3 未安装三行 | Task 8、Task 12 |
| 4.4 默认一句结论，路径不挡发布 | Task 8、Task 12 |
| 4.5 / 第 3 节 先关掉 | Task 5、Task 8、Task 12 |
| 第 5 节 拼接位置 | Task 4 |
| 第 6 节 一稿与 edited | Task 9、Task 12 |
| 第 7 节 状态机 | Task 10 |
| 第 8 节 归因表与三处盖戳 | Task 2 |
| 战报赞为 0、再学只含 playbook | Task 11 |
| 重新出片 | Task 10 |
| 第二期 N=3、两条回放题、相对基线 | 不在本计划 |

## 不做

- 不启动真实 `dsh` 的集成测试作为合并门槛。本机手动：安装 `dsh` 后打开 `/pattern-lab`，贴一段不含「10 倍」的文案，确认能发布并在主页出稿。
- 不改评分门槛，不把打法写入 `build_methodology_prompt_section`。
