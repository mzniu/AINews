# 热榜节点：从 TopHub 目录挑选（Board Picker）

> 日期：2026-09-19  
> 状态：**v0.2 有条件批准（首席架构师审阅修订版）**  
> 范围：系统配置「热榜雷达」里用可搜索弹窗从 TopHub 全量目录挑选热榜，替代手填 `hashid` / 节点 ID  
> 前置：`master` 已含 M0 多行业（`packs/*/hot_radar.boards` + `load_merged_hot_radar_config` 的 effective overlay）  
> 审阅人：首席架构师 Agent  
> 产品确认：弹窗搜索多选；当前行业已选列表可删默认项；该行业一旦保存过，以用户选择为准

## 0. 审阅结论摘要

| 项 | 结论 |
|----|------|
| 总体评价 | **有条件批准** — 方案 A 方向正确；v0.1 的加载/保存 Interface 未闭合 |
| 架构方向 | 方案 A（TopHub 目录独立 Module + `selected_by_industry` 作用户最后覆盖）**采纳** |
| **关键修正 1** | `selected` 在 `load_merged_hot_radar_config()` 内、**effective overlay 之后**生效；禁止只改 `enabled_boards()` |
| **关键修正 2** | `PUT boards[]` = 当前行业已选卡片，**不是** `local.boards` 整表替换 |
| **关键修正 3** | 键缺省 ≠ `[]`；无 selected 时设置页只展示 pack `add` 子集 |
| 前置门禁 | 单测走 `enabled_boards(load_merged_hot_radar_config())`，且不得写在 `AINEWS_DISABLE_EFFECTIVE_CONFIG=1` 的 autouse 夹具里测 overlay |

详见文末「首席架构师审阅」。Blocking #1–#4 与 High #5–#8 已写入正文。

## 目标

运营在「系统配置 → 热榜雷达 → 热榜节点」能：

1. **看见已选热榜的名称**（平台名 · 榜单名），而不是 `hashid`。
2. **点「添加热榜」**，从 TopHub 全量节点目录搜索并多选加入。
3. **启用 / 停用 / 从当前行业移除**，不必手写 ID。
4. 保存后，刷新热榜实际拉取的就是这份已选（启用）列表。

**不在本轮做**：改热榜匹配算法、评分权重、自动发现域名映射、TopHub 以外的 provider、把 5000 节点提交进 Git、并发分页、改 `apply_catalog_ref_ops` 全局语义、把 selected 写入 pack YAML / effective JSON。

## 成功指标

| 指标 | 说明 |
|------|------|
| 添加路径 | 不打开 YAML、不粘贴 hashid，即可把一个 TopHub 节点加入已选 |
| 运行一致 | 保存后 `enabled_boards(load_merged_hot_radar_config())` 与设置页已选（启用）列表一致；`refresh_effective_cache()` 之后再读仍一致 |
| 行业不串台 | 在 `tech/ai` 增删热榜，不抹掉 `finance/macro` 的 pack 引用与 selected |
| 目录可刷新 | 无缓存或点「刷新目录」时能从 TopHub `/nodes` 拉到节点；有缓存时打开弹窗秒开 |

## 背景：现网问题

### 设置页

[`static/js/settings_hot_radar.js`](../../../static/js/settings_hot_radar.js) 每张卡片暴露「节点 ID / TopHub hashid / 平台名称 / 榜单名称」。`addBoardRow()` 生成空 `hashid`，用户必须自己去 TopHub 查。没有删除按钮。

仓库内已有离线脚本 [`scripts/_fetch_tophub_nodes.py`](../../../scripts/_fetch_tophub_nodes.py)（`GET https://api.tophubdata.com/nodes?p=`），评估报告约 **5000** 个节点。脚本有 `page > 50` 截断（约 1000 条）。设置页没有调用这条目录接口。

### 配置分层（当前 master）

```
config/hot_radar.yaml          # repo 默认 catalog（7 个 AI 榜）
hot_radar.local.yaml           # 用户覆盖（API Key、boards）
packs/{l1}/{l2}.yaml           # 行业包 boards.add/remove/patch（仅 ref 已有 id）
data/cache/effective/...       # effective overlay
```

[`load_merged_hot_radar_config()`](../../../services/ingestion/hot_radar_settings.py) 顺序：

1. `merge(base, local)`
2. 若未禁用 overlay：再 `merge(merged, hot_radar_from_effective_cache())`

这使 **pack/effective 盖在 local 之上**，与 M0 §6.2「`*.local.yaml` 用户级最后覆盖」相反。`refresh_hot_radar()` 走 `load_hot_radar_config()` → `enabled_boards(cfg)`，**信任传入的 `cfg["boards"]`**，不会再读 local。

[`apply_catalog_ref_ops`](../../../services/industry/config_loader.py) 在 pack 有 `add` 时：先把 catalog 里所有 board `enabled=false`，再只把 pack `add` 的 ref 打开。不在 pack `add` 里的节点（包括用户刚加的）运行时会被关掉。未 `add` 的行**不会删除**，只是停用后仍留在列表里。

[`public_hot_radar_settings()`](../../../services/ingestion/hot_radar_settings.py) **不读** effective overlay。设置页展示 base+local，运行时用 pack 过滤后的列表。

[`save_hot_radar_settings()`](../../../services/ingestion/hot_radar_settings.py) 每次从空 dict 重建 local 文件，只从 existing 抄 `access_key`；`"boards" in payload` 时整表替换 `local["boards"]`。

### 产品决策（本功能）

| # | 决策 |
|---|------|
| 1 | 「添加热榜」打开 **可搜索多选弹窗**，不是整页 5000 行目录，也不是卡片内 typeahead |
| 2 | **当前行业已选列表是唯一真相（该行业一旦保存过，含空列表）**：可移除默认的新浪 / IT之家 等。从未写下该行业 selected 键时，仍用 pack 默认 `add` |
| 3 | 目录数据走 **后端缓存**，不每次打开弹窗打满 TopHub 分页，也不把 `_tophub_nodes.json` 提交进仓库 |

## 方案对比

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A. 目录 catalog ∪ 行业已选（推荐）** | TopHub 节点缓存独立模块；`local.yaml` 只追加用户新节点；**当前行业已选**写在 local 的 per-industry 列表，在 effective overlay **之后**投影 | 与 M0「pack 只 ref catalog」兼容；切行业不丢另一行业的 ref；云端 pack 落盘不覆盖用户选择 | 比「local.boards 整表替换」多一个键 |
| B. `local.boards` 整表替换 | 设置页列表 = `local.boards`，有该键就不再 merge base / pack | 实现短 | 删掉 `sina_ai` 后 `finance/macro` 的 `ref: sina_ai` 解析失败 |
| C. 改 pack YAML 的 `add` | 挑选结果写进 `data/cache/packs/{l1}/{l2}.yaml` | 和 effective 路径一致 | `apply_cloud_manifest_to_cache()` 会覆盖用户选择 |

采用 **A**。本功能是在补 M0 boards 路径上「effective 最后覆盖」的 inversion，不是新发明一层。

## 架构

```
设置页「添加热榜」
        │
        ▼
GET /api/ingestion/hot-radar/nodes[?refresh=1]
        │
        ▼
list_tophub_nodes()          ← 目录 Module（返回 items/stale/fetched_at）
        │  缓存未命中 / refresh
        ▼
TopHub GET /nodes?p=         （Authorization = 已有 API Key）
        │
        ▼
data/cache/tophub_nodes.json （原子落盘；gitignore 的 data/ 下）

设置页「保存热榜配置」
        │
        ▼
PUT /api/ingestion/hot-radar/settings
  boards[] = 当前行业已选卡片（含停用，不含已删除）
        │
        ▼
hot_radar.local.yaml
  boards: 仅 upsert 用户新节点（hashid 不在 repo catalog）
  selected_by_industry:
    tech/ai: [{id, enabled}, ...]
        │
        ▼
load_merged = merge(base, local) → overlay effective → apply_selected_boards
        │
        ▼
enabled_boards(cfg) / public_hot_radar_settings() 只消费这一份 boards
```

`refresh_effective_cache()` 保存后可调用（让 cache 看见新 catalog 行），**不是**「用户意图已生效」的充分条件。真正生效靠 `apply_selected_boards` 挂在 `load_merged_hot_radar_config()` 末尾。

切行业只改 `active_industry_id` + effective cache，不碰 `hot_radar.local.yaml`。云端 pack 更新只影响 **尚未写下该行业 selected 键** 的默认列表。

### Module 1：`tophub_catalog`（新）

路径：`services/ingestion/tophub_catalog.py`

**Interface**（调用方与测试只面对这些；route **禁止**直接读缓存文件）：

```python
class TophubAuthError(Exception): ...
class TophubCatalogError(Exception): ...

@dataclass(frozen=True)
class TophubNodeCatalog:
    items: list[dict[str, Any]]   # {hashid, name, display, domain, logo}
    stale: bool
    fetched_at: str               # ISO-8601

def list_tophub_nodes(
    *,
    refresh: bool = False,
    access_key: str,
    api_base_url: str,
) -> TophubNodeCatalog:
    """Raise TophubAuthError if access_key empty; TophubCatalogError if fetch fails with no cache."""
```

**Implementation 隐藏**：分页 `p` 直到短页（`<20`）；**不要**复制脚本的 `page > 50`。TTL 24h。损坏 JSON 重拉。内存凑齐全量后 tempfile + replace；中途失败不落半截文件。总墙钟 60–90s：超时且无旧缓存 → 抛错；有旧缓存 → 返回 `stale=true`。无 Key 文案对齐 `hot_radar_service.py`（「TopHub API Key 未配置…」）。

`list_tophub_nodes` **只收** `access_key` + `api_base_url`（route 先 `resolve_tophub_access_key`），不要传入整份 hot-radar config，避免 catalog `import load_merged`。

**本轮不做**并发分页。

**不**把目录写进 `hot_radar.yaml`。那份文件继续当 repo 默认 catalog（给 pack `ref` 用）。

### Module 2：热榜设置 persist（改现有）

路径：[`services/ingestion/hot_radar_settings.py`](../../../services/ingestion/hot_radar_settings.py)

在 `hot_radar.local.yaml` 增加 `selected_by_industry`。`boards` 只承载 **用户新加的 catalog 行**（id = hashid），不是设置页卡片的整表拷贝。

```yaml
version: 1
access_key: "..."
boards:
  - id: WnBe01o371
    hashid: WnBe01o371
    name: 微信
    display: 24h热文榜
selected_by_industry:
  tech/ai:
    - {id: sina_ai, enabled: true}
    - {id: WnBe01o371, enabled: false}
  finance/macro:
    - {id: sina_ai, enabled: true}
```

| 键 | 含义 |
|----|------|
| `boards` | 用户 catalog **增量**（hashid 不在 repo `hot_radar.yaml` 的节点）。已有 catalog id（如 `sina_ai`）**禁止**用当前页的 `name`/`display`/`enabled` 回写全局 local.boards，以免 `finance/macro` 的 pack `patch`（`display: 宏观舆情`）与 `tech/ai` 互相污染。`weight` 等仍待在 base / pack。 |
| `selected_by_industry.<active>` | 当前行业已加入设置页的列表（有序）。每项 `{id, enabled}`。判断用 **`active in selected_by_industry`**（键是否存在），禁止 `if selected_map.get(active):`——空列表 `[]` 表示用户删光，**不得**回退 pack。 |

#### 运行时加载（唯一 Interface）

`load_merged_hot_radar_config()` 必须是 enablement 的唯一 seam。`refresh_hot_radar` / `hot_radar_batch` / `hot_radar_discovery` 都走 `enabled_boards(cfg)`，只消费这份 `cfg["boards"]`。

```
local = load_hot_radar_local()
merged = merge_hot_radar_config(load_hot_radar_base(), local)
effective = hot_radar_from_effective_cache()
if effective:
    merged = merge_hot_radar_config(merged, effective)   # 仍合并 pack 的非 boards 键与 overlay boards
selected_map = local.get("selected_by_industry") or {}
if active_industry_id in selected_map:                   # 键存在，即使 []
    merged["boards"] = project_selected(catalog, selected_map[active_industry_id])
# else: merged["boards"] 保持 overlay（现网 M0b）
```

`project_selected`：按 selected 顺序从 catalog（base ∪ local.boards）取行；`enabled` 以 selected 项为准；**不在列表中的行不进入运行时**（含 pack `add`）。display/name：catalog 行 → **再套当前行业 pack `patch`** → 再用 selected 的 `enabled`。

`apply_catalog_ref_ops` **保持原样**（ingestion sources 共用）。不要改它的全局语义。

#### `public_hot_radar_settings()`

与 `load_merged` **同源**，并返回：

- `active_industry_id`
- `selection_source`: `"user"` | `"pack"`
- `boards`：有 selected → selected 全量（含停用）；**无 selected → 仅 pack `add`（及 patch）解析出的子集**，不是 disable-all 后的 7 行残缺启用态。

运行时拉取只用 `enabled: true` 的项。

#### 保存四步（禁止 `local["boards"] = payload["boards"]`）

`PUT` body 仍发 `boards: [{hashid, name, display, enabled, id?}]` = **当前行业已选卡片**（含停用、不含已点删除的）。前端不必懂 pack 格式。服务端不变量：这是 selected，不是 catalog。

1. `existing = load_hot_radar_local()`，保留其它行业 `selected_by_industry`、以及未在本次 payload 出现的 local catalog 行；其它键（discovery / cron / access_key）按现网逻辑合并，**禁止**从空 dict 重建整文件以致丢掉新键。
2. 按 **hashid** 在 `base ∪ existing.boards` 查已有 `id`，命中则沿用（`sina_ai`），否则 `id = hashid`。**只 upsert 不在 repo catalog 的新节点**进 `local.boards`（可写 name/display）。已有 catalog id **不**回写 name/display/enabled。
3. `selected_by_industry[active] = [{id, enabled}, ...]`（按 payload 顺序；已删 = 不在 payload）。
4. 可选 GC（非门禁）：用户自加节点若不被任何行业 selected 引用，才从 local `boards` 删除。

保存成功后：可 `refresh_effective_cache()` + `worker.refresh_schedules()`；前端用 `public` 响应（或再 GET）`renderBoards`，以便服务端把 hashid 规范成 `sina_ai`。

discovery-only PUT（不带 `boards`）不得丢掉 `selected_by_industry`。

### Module 3：HTTP

路径：[`api/routes/hot_radar_routes.py`](../../../api/routes/hot_radar_routes.py)

```
GET /api/ingestion/hot-radar/nodes?refresh=false
```

成功：把 `TophubNodeCatalog` 展开为 `{success, stale, fetched_at, count, items}`。无 Key → **400**（`TophubAuthError`）。无缓存且拉取失败/超时 → **502**。

`PUT /hot-radar/settings`：`boards` = 当前行业已选卡片；selected 由服务端按 active industry 推导。GET settings 增加 `active_industry_id`、`selection_source`。

## 页面结构与交互

路径：[`static/settings.html`](../../../static/settings.html) 热榜雷达面板 + [`static/js/settings_hot_radar.js`](../../../static/js/settings_hot_radar.js)。

### 已选列表

- 标题改为「已选热榜」；按钮文案「添加热榜」。
- 卡片只显示：`name · display`，可选一行 `domain` hint；启用/停用；**从当前行业移除**。
- **不渲染** 节点 ID、hashid 输入框。hashid / id 放在内存 state。
- 说明改为：从 TopHub 目录挑选；保存后用于当前垂类的热榜刷新。

### 弹窗

自建 overlay，用 `.app-modal-overlay.is-open`。加宽修饰类（约 `min(720px, 92vw)`），只加一处 CSS。不要为 modal 引入 `ui.js`（`AppUI.openModal` 不加 `is-open`，且设置页未引入该脚本）。

1. 搜索框：过滤 `name` / `display` / `domain`（前端，大小写不敏感）。
2. 已在已选列表中的项标记「已添加」，不可再勾。
3. 空搜索不渲染 5000 行，只提示「输入平台或榜单名称」。有关键词后最多展示 **100** 条。
4. 「刷新目录」→ `GET .../nodes?refresh=true`。
5. 「加入」按 id 规则 upsert 进内存已选列表并关闭。
6. 无 Key：不请求目录，提示先填 TopHub API Key。
7. 冷启动：显示「正在从 TopHub 拉取目录…」（后端已有总墙钟）。

### id 规则

- catalog（base ∪ local）已有相同 `hashid`：沿用其 `id`（例如 `sina_ai`）。
- 否则 `id = hashid`。禁止 `board_${Date.now()}`。

## 错误与边界

| 情况 | 行为 |
|------|------|
| 未配置 Key | 弹窗与 `/nodes` 均明确报错；已选列表仍可删/停用/保存 |
| TopHub 分页中断 / 超时 | 不落半截缓存；有旧缓存则 `stale`；否则 502 |
| 重复挑选同一 hashid | upsert，不复制卡片 |
| 切换垂类 | 重载后：有该行业 selected 键则展示之；否则展示 pack `add` 子集 |
| 云端同步行业包 | 不改 local.yaml；已写下 selected 的行业不被 pack 加回已删榜 |
| 保存时 effective 缓存刷新失败 | 仍写出 local.yaml；用户意图靠 `load_merged` 末尾的 selected 投影生效 |
| selected=`[]` | `enabled_boards` 为空，public 列表为空，**不**回退 pack |

## 文件变更

| 文件 | 变更 |
|------|------|
| `services/ingestion/tophub_catalog.py` | 新建：深 Module（items/stale/fetched_at、原子缓存、总墙钟） |
| `services/ingestion/hot_radar_settings.py` | `apply_selected_boards` 挂在 `load_merged`；`public_*` 同源；保存四步 |
| `api/routes/hot_radar_routes.py` | `GET .../nodes` |
| `static/js/settings_hot_radar.js` | 弹窗挑选、卡片去 ID、删除、保存后用响应重绘 |
| `static/settings.html` | 文案 |
| `static/css/app_shell.css` | 一处弹窗加宽修饰类 |
| `tests/test_tophub_catalog.py` | 新建：mock 分页、TTL、损坏 JSON、半截不落盘、无 Key |
| `tests/test_hot_radar_api.py` | 现有文件追加 `/nodes` 400/200 |
| `tests/test_industry_hot_radar_effective.py` | selected 覆盖 pack；空列表；跨行业 PUT；切回仍无已删榜 |
| `tests/test_hot_radar_settings.py` | 仅测无 overlay 的 persist（discovery-only PUT 不丢 selected）；**禁止**在 autouse disable 夹具里测 pack overlay |

## 测试要点

1. **目录**：两页 mock 合成；TTL 命中不打网；`refresh=True` 再打；损坏 JSON 重拉；中途失败不落半截文件。
2. **无 Key**：`TophubAuthError` / HTTP 400。
3. **selected 覆盖 pack**（`test_industry_hot_radar_effective.py`，先 `write_effective_cache`）：pack `add` 含 `sina_ai`，local selected 只有 `{id: ithome_ai, enabled: true}` → `enabled_boards(load_merged_hot_radar_config())` 无新浪；随后 `refresh_effective_cache()` **再读一次仍无**。
4. **停用 ≠ 删除**：selected 含 `{id: sina_ai, enabled: false}` → public 仍有停用卡片；`enabled_boards` 不含它。
5. **空列表**：`tech/ai: []` → `enabled_boards` 为空，不回退 pack 7 榜。
6. **从未写过 selected**：`test_enabled_boards_follow_effective_pack` 仍过。
7. **新节点**：selected 含 `WnBe01o371` → `enabled_boards` 含微信榜（pack `add` 没有它也不能禁用）。
8. **跨行业**：`tech/ai` PUT 后 `finance/macro` 的 selected 仍在；discovery-only PUT 不丢 selected。
9. **切行业回归**：`tech/ai` 已保存且无新浪 → switch `finance/macro` → sync pack → 切回 `tech/ai` → 仍无新浪。
10. **设置 roundtrip**：PUT 再 GET，`selection_source=user`，响应不含明文 Key；只传 hashid 时服务端解析为 `sina_ai`。

## 实施顺序

1. `tophub_catalog` + 单测（不碰 UI）。High #5–#8 已进规格，不阻塞本步。
2. `apply_selected_boards` 挂在 `load_merged` + 保存四步 + 行业回归测（Blocking 门禁）。
3. `GET /nodes`。
4. 设置页弹窗与卡片。

## 修订历史

| 版本 | 日期 | 摘要 |
|------|------|------|
| v0.1 | 2026-09-19 | 初稿：弹窗多选 + 后端目录缓存 + per-industry selected |
| v0.2 | 2026-09-19 | 首席架构师审阅修订：selected 在 effective 之后投影；保存四步；空列表≠缺省；catalog Interface 含 stale |

---

## 首席架构师审阅

> 审阅日期：2026-09-19  
> 审阅人：首席架构师 Agent  
> 对照：当前 `master`（含 M0 多行业）+ 本文件 v0.1  
> 结论：**有条件批准进入实现** — 方案 A 方向正确，且与 M0 §6.2「`*.local.yaml` 用户级最后覆盖」一致；v0.1 把 `refresh_effective_cache()` 写成充分条件，现网 `load_merged` 仍会把 effective boards 盖在 local 之上。v0.2 已按下列 Blocking / High 修订正文。

### 0.1 审阅发现与处置

| # | 严重度 | 问题 | v0.2 修订 |
|---|--------|------|-----------|
| 1 | **Blocking** | `load_merged` 在 effective overlay 之后仍按 id 覆盖；`enabled_boards(cfg)` 信任传入 boards；`refresh_effective_cache()` 会加重撤销用户删除/新节点 | `apply_selected_boards` 挂在 `load_merged` 末尾；refresh cache 不再是生效充分条件 |
| 2 | **Blocking** | `save_hot_radar_settings` 整文件重建 + 整表替换 `local.boards`；缺 id 时 `id=hashid` 与 `sina_ai` 双行 | 保存四步；payload.boards ≠ local.boards |
| 3 | **Blocking** | `if selected.get(active)` 把 `[]` 当缺省，删光后回退 pack | 用 `active in selected_map` |
| 4 | **Blocking** | 无 selected 时 public 若等于 disable-all 全 catalog，设置页出现 6 张停用卡，一点保存就冻结 pack 互斥 | 无 selected 时 public = pack `add` 子集 |
| 5 | **High** | 全局 local.boards 回写 name/display 污染 pack patch | 已有 catalog id 禁止回写；新节点才 upsert |
| 6 | **High** | overlay 测写在 `AINEWS_DISABLE_EFFECTIVE_CONFIG=1` 夹具里会假绿 | overlay 用例进 `test_industry_hot_radar_effective.py` |
| 7 | **High** | catalog Interface 只返回 list，route 会偷看缓存文件；`page>50` 截断；无总超时 | `TophubNodeCatalog`；短页结束；原子落盘；60–90s 墙钟 |
| 8 | **High** | 切行业 / 云端 pack 若 #1 未修会盖掉 selected | 切行业不碰 local；已写 selected 的行业不被 pack 加回 |
| 9 | **Medium** | PUT `boards[]` 不变量变了 | GET 增加 `selection_source` |
| 10 | **Medium** | catalog 深度来自 TTL/原子缓存/stale，须留在 Module 内 | 见 Module 1 |
| 11 | **Medium** | 现网无删除按钮；勿引入 `ui.js` | 已写入交互 |
| 12 | **Low** | 保存后不重绘，id 规范化不同步 | 保存成功用 public 重绘 |
| 13 | **Low** | 并发分页 / 双 CSS 待定 | 本轮不做并发；CSS 只加一处 |

### 0.2 Deep module / seam / locality

| 检查 | 评估 |
|------|------|
| `tophub_catalog` | v0.2 Interface 含 stale/fetched_at + 领域错误后为深 Module；缓存路径不是外部 Interface |
| Enablement | `apply_selected_boards` 是唯一 seam；`public_*` / `enabled_boards(cfg)` / 刷新路径共用 |
| Pack overlay | `apply_catalog_ref_ops` 不改；selected 不写进 `data/cache/packs/` |
| `PUT boards[]` | 类型兼容，不变量变了；用保存四步 + `selection_source` 写进 Interface |
| YAGNI | 不改匹配/发现/pack 全局语义/5000 节点入库 — 保持 |

### 0.3 签核

**写入 Blocking #1–#4 与 High #5–#8 之后：可以开工（YES）。**  
下一步：按实施顺序从 `tophub_catalog` + 单测开始。
