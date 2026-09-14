# 双维度评分与传播优化 — 技术设计文档

**版本**: v0.1  
**日期**: 2026-09-05  
**状态**: Draft — 待架构 Review  
**依据**: 10万+ / 1万+ 爆款数据分析 + 传播学教授 Review

---

## 1. 背景与问题陈述

### 1.1 数据结论

对 489 条已发布且有指标的内容分析：

| 发现 | 数据 |
|:---|:---|
| 评分与播放无关 | 各播放档位 `score_total` 中位数均为 86±1 |
| A 级命中率高于 S 级 | 1万+: A 16.0% vs S 11.8%；10万+: A 2.83% vs S 1.84% |
| 维度饱和 | 7/10 维度在爆款与普通内容间无区分力 |
| 平台差异大于评分差异 | 快手 85-90 分内容 1万+ 为 0；视频号占 10万+ 的 60% |

### 1.2 根因

当前系统将两种不同价值压入单一 `score_total`：

- **行业质量分**（Professional News Values）：时效、显著性、突破性、AI 相关性
- **大众传播力**（Shareability）：社交货币、情绪唤醒、人物故事、公共议题

自动化流水线（出片、发布）仅依赖 `score_grade` / `score_total`，无法区分「行业好稿」与「大众爆款」。

### 1.3 目标

1. 拆分 `industry_score` 与 `viral_potential`，保留向后兼容
2. 自动化决策改为双维度门控 + 平台分流
3. 修正已知误伤（非 AI 公共议题、配图惩罚、热榜权重）
4. 用 63 条 1万+ 样本回测验证

### 1.4 非目标（本阶段不做）

- 不引入机器学习回归模型（样本量不足）
- 不改动口播/渲染模板（Plan B 已完成）
- 不暂停快手发布
- 不恢复口播「突发/炸裂」开场

---

## 2. 方案概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Ingest / Rescore                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │     score_article()         │  规则引擎（现有 10 维）
              │  → industry_total/grade     │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  score_viral_potential()    │  新增：分享动机 + 钩子门槛
              │  → viral_total/grade        │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  optional LLM review        │  结构化 viral 判断
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  persist score_breakdown    │  扩展 JSON，兼容旧字段
              └──────────────┬──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
  ┌──────▼──────┐   ┌────────▼────────┐  ┌──────▼──────┐
  │Media Pipeline│   │ Platform Router │  │ Publish Q   │
  │ 门控         │   │ 平台分流         │  │ 调度        │
  └─────────────┘   └─────────────────┘  └─────────────┘
```

---

## 3. 数据模型

### 3.1 数据库变更

**方案 A（推荐）：仅扩展 JSON，零 migration**

利用现有 `score_breakdown_json` 存储双维度，不新增列：

```json
{
  "profile": "flash_news",
  "industry": {
    "total": 86.6,
    "grade": "S",
    "dimensions": [ "...现有 10 维..." ],
    "bonuses": [],
    "penalties": []
  },
  "viral": {
    "total": 72.0,
    "grade": "B",
    "motives": [
      { "key": "social_currency", "label": "社交货币", "score": 8, "signals": ["600亿"] },
      { "key": "emotional_arousal", "label": "情绪唤醒", "score": 6, "signals": [] },
      { "key": "identity", "label": "身份认同", "score": 4, "signals": [] },
      { "key": "public_issue", "label": "公共议题", "score": 7, "signals": ["Meta"] }
    ],
    "hook_gate": { "passed": true, "subject": true, "number": true, "conflict": true },
    "platform_fit": ["wechat_channels", "douyin"]
  },
  "hot_radar": { "...不变..." },
  "llm": { "...扩展 viral 字段..." },
  "final": {
    "industry_total": 86.6,
    "industry_grade": "S",
    "viral_total": 72.0,
    "viral_grade": "B",
    "publish_tier": "priority",
    "adjusted_by": "rule"
  },
  "total": 86.6,
  "grade": "S"
}
```

顶层 `total` / `grade` **保持现有语义**（= industry），确保所有未改造代码路径不受影响。

**方案 B（可选，Phase 2）**：新增列 `viral_score_total`, `viral_score_grade` 用于索引/筛选。本阶段不实施。

### 3.2 向后兼容

| 消费者 | 兼容策略 |
|:---|:---|
| `score_total` / `score_grade` 列 | 继续写入 industry 值 |
| `should_run_media_pipeline()` | Phase 1 不改签名；内部读 `final.publish_tier` |
| 资讯库 UI | 渐进展示 viral 徽章 |
| 指标分析脚本 | 读 `breakdown.viral` 新字段 |
| 旧 `breakdown.dimensions` | 迁移期双写：顶层 `dimensions` = industry.dimensions |

---

## 4. 行业质量分（Industry Score）

### 4.1 变更摘要

| 项 | 现值 | 新值 | 理由 |
|:---|:---|:---|:---|
| S 级门槛 | 85 | **88** | 消除 S 级通胀（380 条仅 1.84% 爆款） |
| `event_tension` 计分 | 命中即高分 | **阶梯计分** | 消除满分泛滥 |
| `hook` 维度 | 加分项 | **移至 viral 层** | 钩子属于表达属性，非行业质量 |
| `hot_radar` 未命中 | 固定 2 分 | **0 分（中性）** | 未命中不应惩罚 |
| 配图不足惩罚 | 无条件 -6 | **条件豁免** | 突发财经类不应误伤 |
| 非 AI 惩罚 | relevance < 5 → -12 | **公共议题豁免** | 库克卸任类误伤 |

### 4.2 Event Tension 阶梯计分

```python
def _score_event_tension(text, cfg) -> tuple[float, list[str]]:
    signals = _match_signals(text, cfg["event_tension_signals"])
    tier1_hits = _match_tier1(text, cfg)
    n = len(signals)
    if n == 0:
        return 4.0, signals
    if n <= 2:
        score = 6.0
    elif n <= 3:
        score = 8.0
    else:
        score = 8.0 if not tier1_hits else 10.0
    return score, signals
```

### 4.3 公共议题豁免（替代「公司豁免」）

```yaml
public_issue_signals:
  - CEO
  - 卸任
  - 接任
  - 战略转向
  - 监管
  - 禁令
  - 大规模裁员
  - 千人裁员
```

当 `prominence >= 8.5` 且命中 ≥1 个 `public_issue_signals` 时，跳过 `off_topic` 惩罚。

### 4.4 配图惩罚豁免

```yaml
penalties:
  insufficient_images:
    min_images: 3
    points: -6
    exempt_when:
      - timeliness_score_gte: 9
      - has_money_signal: true   # 含亿/万亿/融资/收入/估值
```

### 4.5 Industry 权重调整

`hook` 权重从 0.12 回收，重新分配：

```yaml
weights:
  timeliness: 0.14
  prominence: 0.16
  event_tension: 0.20
  breakthrough: 0.12
  product_heat: 0.10
  relevance: 0.14
  data_signal: 0.04
  creatability: 0.04
  hot_radar: 0.06   # 仅命中时计分，见 4.6
  # hook: 移除，迁至 viral 层
```

### 4.6 Hot Radar 计分改造

| 状态 | 现分 | 新分 |
|:---|:---:|:---:|
| 未命中 | 2.0 | **0.0** |
| rank 21-50 | 5.5 | 5.5 |
| rank 11-20 | 7.0 | 7.0 |
| rank 4-10 | 8.5 | 8.5 |
| rank 1-3 | 10.0 | 10.0 |

角色定位：**入场券**（跟进保障），非爆款预判。保留 `hot_radar` bonus（top3 +3, top10 +1）。

---

## 5. 大众传播力（Viral Potential）

### 5.1 设计原则

- **独立计分**，不并入 industry 权重
- 输出 0–100 分 + V/S/A/B/C 等级
- 基于「分享动机四分法」，非关键词堆砌
- 含「钩子门槛过滤器」（必要条件，非加分）

### 5.2 分享动机四维

| 维度 key | 标签 | 权重 | 信号源 | 示例 |
|:---|:---|:---:|:---|:---|
| `social_currency` | 社交货币 | 0.30 | 超大数字、独家爆料、行业震撼 | 600亿、10万亿、4.75亿 |
| `emotional_arousal` | 情绪唤醒 | 0.25 | 冲突、对抗、翻车、暴涨暴跌 | 裁员、叫停、离职、对峙 |
| `identity` | 身份认同 | 0.25 | 人物故事、群体标签 | 00后、博士、红娘、天才少年 |
| `public_issue` | 公共议题 | 0.20 | 社会级事件、权力更替 | CEO卸任、监管禁令 |

每维 0–10 分，加权 ×10 得 `viral_total`。

### 5.3 信号配置

```yaml
viral_scoring:
  grades:
    S: 75    # viral S = 高传播潜力
    A: 60
    B: 45
    C: 30
  motives:
    social_currency:
      weight: 0.30
      signals:
        magnitude_patterns:
          - pattern: '(\d+(\.\d+)?)\s*万亿'
            score: 10
          - pattern: '(\d+(\.\d+)?)\s*亿'
            score: 8
          - pattern: '(\d{3,})\s*万'
            score: 6
        shock_words: [暴涨, 暴跌, 翻倍, 10倍]
    emotional_arousal:
      weight: 0.25
      signals: [离职, 裁员, 开除, 叫停, 翻车, 对峙, 决裂, 内斗]
    identity:
      weight: 0.25
      signals: [00后, 博士, 红娘, 天才, 少年, 创业, 退款, 结婚]
    public_issue:
      weight: 0.20
      signals: [CEO, 卸任, 接任, 监管, 禁令, 制裁]
      require_tier1: true
```

### 5.4 钩子门槛过滤器（Hook Gate）

**不参与 viral_total 加权**，作为发布资格前置条件：

```python
@dataclass
class HookGateResult:
    passed: bool
    subject: bool    # tier1/celebrity/热词主体
    number: bool     # 标题含 ≥2 位有效数字
    conflict: bool   # 冲突/转折词

def evaluate_hook_gate(title: str, summary: str, cfg) -> HookGateResult:
    ...
    # passed = 三者中至少满足两项
```

| 结果 | 影响 |
|:---|:---|
| `passed = true` | 正常参与 viral 评级 |
| `passed = false` | `viral_grade` 上限为 B（不管动机分多高） |

### 5.5 Viral Bonus

```yaml
viral_bonuses:
  hot_radar_entry:        # 热榜入场券
    min_rank: 20
    points: 5
  multi_source:
    min_articles: 2
    points: 3
  all_motives_present:    # 四维均 ≥ 5
    points: 5
```

### 5.6 代码结构

新文件 `services/ingestion/viral_scorer.py`：

```python
@dataclass
class ViralScoreResult:
    total: float
    grade: str
    motives: list[DimensionScore]
    hook_gate: HookGateResult
    bonuses: list[dict]
    platform_fit: list[str]

def score_viral_potential(
    *,
    title: str,
    summary: str,
    content: str,
    cfg: dict,
    hot_radar: HotRadarMatch | None = None,
    prominence_score: float = 0,
) -> ViralScoreResult: ...
```

在 `score_service.apply_score_to_article()` 中，`score_article()` 之后调用 `score_viral_potential()`，合并入 breakdown。

---

## 6. LLM 增强（Viral 维度）

### 6.1 触发条件

保持现有 LLM 触发逻辑不变（API `use_llm=true`、ingest `auto_llm_for_sa`），扩展 prompt 输出：

```json
{
  "flash_verdict": "...",
  "comment": "...",
  "viral_assessment": {
    "mass_appeal": "high|medium|low",
    "share_motivation": "social_currency|emotional|identity|public_issue",
    "share_motivation_secondary": "emotional",
    "platform_fit": ["wechat_channels", "douyin"],
    "reframe_suggestion": "视频号强调转发价值，抖音强调冲突数字"
  },
  "adjusted_grade": "S",
  "adjusted_score": 88,
  "viral_adjusted_grade": "A",
  "viral_adjusted_score": 68
}
```

### 6.2 LLM 调整规则

- `viral_adjusted_score` 仅在 `|llm - rule| > 10` 时生效（防止 LLM 过度干预）
- LLM 不可将 `hook_gate.passed = false` 的条目提升到 viral A 以上
- Industry LLM 调整保持现有 `_apply_llm_adjustment()` 逻辑

### 6.3 配置修复

将 `post_score_automation.auto_llm` **接入代码**（当前为死配置），或标记 deprecated 并统一由 `ingestion_sources.yaml` 控制。本设计采用：**读取 `post_score_automation.auto_llm` 作为优先配置，fallback 到 ingest 配置**。

---

## 7. 自动化门控改造

### 7.1 Publish Tier 计算

```python
def compute_publish_tier(industry_grade, viral_grade, hook_gate, cfg) -> str:
    """
    Returns: 'viral_priority' | 'industry_priority' | 'standard' | 'skip'
    """
```

| publish_tier | 条件 | 行为 |
|:---|:---|:---|
| `viral_priority` | viral ≥ A 且 hook_gate.passed | 全平台优先发布，缩短间隔 |
| `industry_priority` | industry ≥ S 且 viral < B | 出片但仅抖音/技术向平台 |
| `standard` | industry ≥ A 或 score ≥ 80 | 现有默认行为 |
| `skip` | industry < B 且 viral < C | 不出片 |

### 7.2 Media Pipeline 门控

改造 `should_run_media_pipeline()`：

```python
def should_run_media_pipeline(
    *,
    final_grade: str,
    final_total: float,
    viral_grade: str | None = None,
    publish_tier: str | None = None,
    config: dict | None = None,
) -> bool:
    # 1. publish_tier == 'skip' → False
    # 2. publish_tier in ('viral_priority', 'industry_priority') → True
    # 3. fallback 现有 grade/score 逻辑
```

### 7.3 Auto Publish 平台分流

新文件 `services/publishing/platform_router.py`：

```python
PLATFORM_CONTENT_MATRIX = {
    "wechat_channels": {
        "prefer_motives": ["emotional_arousal", "public_issue", "identity"],
        "min_viral_grade": "B",
    },
    "douyin": {
        "prefer_motives": ["social_currency", "emotional_arousal"],
        "min_viral_grade": "C",
    },
    "kuaishou": {
        "prefer_motives": ["identity", "social_currency"],
        "min_viral_grade": "C",
    },
}

def select_publish_platforms(
  *,
  viral_result: ViralScoreResult,
  publish_tier: str,
  active_accounts: list[PublisherAccount],
) -> list[PublisherAccount]:
    ...
```

改造 `maybe_enqueue_auto_publish_jobs()`：不再为所有 active 账号创建 job，而是经 `select_publish_platforms()` 过滤。

### 7.4 同题多发策略

```yaml
post_score_automation:
  auto_publish:
    cross_platform:
      enabled: true
      min_viral_grade: A       # 同题双发门槛
      stagger_minutes: 90      # 平台间发布间隔
      reframe_titles: true     # 启用平台标题适配（调用 content_generation）
```

当 Story 内已有 sibling 在某平台发布成功，且当前文章 `viral_grade >= A`：
- 自动为**尚未覆盖的平台**创建 publish job
- 间隔 ≥ 90 分钟
- 标题经 `reframe_for_platform()` 适配（视频号偏分享、抖音偏冲突）

---

## 8. API 变更

### 8.1 响应扩展

`GET /api/ingestion/articles` 每条增加：

```json
{
  "score_total": 86.6,
  "score_grade": "S",
  "viral_score_total": 72.0,
  "viral_score_grade": "B",
  "publish_tier": "industry_priority"
}
```

实现：从 `score_breakdown_json.final` 解析，不新增 DB 列。

### 8.2 筛选扩展

```
GET /api/ingestion/articles?min_viral_grade=A&publish_tier=viral_priority
```

Phase 1 在应用层过滤（JSON 解析）；Phase 2 加 DB 列 + 索引。

### 8.3 Settings API

`GET/PUT /api/ingestion/scoring/settings` 增加 `viral_scoring` 段。

---

## 9. 配置变更汇总

```yaml
# config/article_scoring.yaml 新增/修改段

grades:
  S: 88    # 原 85
  A: 70
  B: 55
  C: 40

viral_scoring:
  enabled: true
  grades: { S: 75, A: 60, B: 45, C: 30 }
  motives: { ... }
  hook_gate: { min_dimensions: 2 }
  bonuses: { ... }

public_issue_signals: [ ... ]

penalties:
  insufficient_images:
  exempt_when: [ ... ]
  off_topic:
    exempt_public_issue: true

post_score_automation:
  auto_llm:
    enabled: true          # 接入代码
    min_grade: A
  media_pipeline:
    trigger:
      min_grade: S
      min_score: 80
      min_viral_grade: B   # 新增
      logic: or
  auto_publish:
    min_grade: S
    cross_platform: { ... }
    platform_router:
      enabled: true
```

---

## 10. 实施计划

### Phase 1 — 核心（1 周）

| 任务 | 文件 | 估时 |
|:---|:---|:---:|
| `viral_scorer.py` + 测试 | 新建 | 1d |
| `article_scorer.py` 改造（阶梯/event/hot_radar/惩罚豁免） | 修改 | 1d |
| `score_service.py` 合并双维度 | 修改 | 0.5d |
| `score_breakdown_json` 结构迁移 + 兼容 | 修改 | 0.5d |
| 回测脚本：63 条 1万+ 验证 | 新建 | 0.5d |
| LLM prompt 扩展 | 修改 | 0.5d |
| 配置更新 + scoring_presets 调整 | 修改 | 0.5d |

### Phase 2 — 自动化（1 周）

| 任务 | 文件 | 估时 |
|:---|:---|:---:|
| `publish_tier` 计算 | 新建 | 0.5d |
| `should_run_media_pipeline()` 改造 | 修改 | 0.5d |
| `platform_router.py` | 新建 | 1d |
| `auto_publish.py` 平台分流 | 修改 | 1d |
| 同题多发 + stagger | 修改 | 1d |
| API 响应扩展 | 修改 | 0.5d |
| UI 展示 viral 徽章 | 修改 | 1d |

### Phase 3 — 验证与调优（持续）

- 运行 2 周 A/B：旧门控 vs 新门控
- 对比 1万+ / 10万+ 命中率
- 根据数据调整 `viral_scoring.grades` 阈值

---

## 11. 测试策略

### 11.1 单元测试

| 测试文件 | 覆盖 |
|:---|:---|
| `test_viral_scorer.py` | 四维动机、hook_gate、bonus |
| `test_article_scorer.py` | 阶梯 event_tension、公共议题豁免、热榜 0 分 |
| `test_publish_tier.py` | tier 计算逻辑 |
| `test_platform_router.py` | 平台选择矩阵 |

### 11.2 回测基准

用 `data/publish/viral_10k_analysis.json`（63 条）验证：

| 指标 | 现系统 | 目标 |
|:---|:---:|:---:|
| 10万+ 在 viral_priority 占比 | N/A | ≥ 80%（8/10） |
| 1万+ 在 viral≥B 或 industry≥S 占比 | ~100% | 维持 ≥ 95% |
| D 级误杀（库克卸任）viral_grade | N/A | ≥ B |
| 高分低播（混元440MB）publish_tier | viral_priority | industry_priority |

### 11.3 回归测试

- 现有 `test_ingestion_article_scorer.py` 全部通过
- `test_publishing_*` 不受影响
- 旧 breakdown JSON 解析不崩溃

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|:---|:---|:---|
| S 门槛 85→88 导致出片量减少 | 产能下降 | 用 viral_priority 补回真正爆款通道 |
| 双维度增加 ingest 耗时 | 延迟 | viral_scorer 纯规则，< 5ms |
| LLM 输出不稳定 | 错误分级 | 调整阈值 > 10 分才生效 |
| 平台分流减少发布量 | 曝光下降 | 快手维持全发；仅高 viral 限平台 |
| JSON 膨胀 | 存储 | 仅新增 ~500 bytes/条 |
| 旧脚本读 breakdown 失败 | 分析中断 | 顶层 `total`/`grade`/`dimensions` 双写 |

---

## 13. 开放问题

1. `hook` 从 industry 移除后，现有 `viral_spread` preset 如何映射？
2. 是否在资讯库 UI 默认展示双分，还是仅管理员可见？
3. 同题多发「标题再编码」是否调用 LLM（有成本）或纯规则替换？
4. Phase 2 是否为 `viral_score_grade` 加 DB 列和索引？

---

## 附录 A：文件变更清单

| 操作 | 路径 |
|:---|:---|
| 新建 | `services/ingestion/viral_scorer.py` |
| 新建 | `services/publishing/platform_router.py` |
| 新建 | `services/ingestion/publish_tier.py` |
| 新建 | `tests/test_viral_scorer.py` |
| 新建 | `tests/test_platform_router.py` |
| 新建 | `tests/test_publish_tier.py` |
| 修改 | `services/ingestion/article_scorer.py` |
| 修改 | `services/ingestion/score_service.py` |
| 修改 | `services/ingestion/article_score_llm.py` |
| 修改 | `services/ingestion/media_pipeline_trigger.py` |
| 修改 | `services/publishing/auto_publish.py` |
| 修改 | `services/ingestion/scoring_presets.py` |
| 修改 | `config/article_scoring.yaml` |
| 修改 | `api/routes/ingestion_routes.py` |
| 修改 | `api/schemas/ingestion_models.py` |
| 修改 | `static/js/ingestion_library.js` |
| 修改 | `docs/article_scoring_criteria.md` |
