# Token 用量统计设计

> 日期：2026-08-24  
> 状态：待确认后实施  
> 范围：系统配置页新增「用量统计」；统计已配置语言模型与视觉（多模态）模型的实际 token 消耗

## 目标

运营在系统配置里能看到：**哪个模型、哪类任务、用了多少 token**。数字来自接口返回的 `usage`，不是本地估算。覆盖系统配置里启用的语言模型和视觉模型，以及仍走 `.env` DeepSeek 的旧调用路径。

不在本轮做：按厂商账单拉数、人民币成本、导出 CSV、按文章钻取。

## 背景

- 模型配置在 `config/models.local.yaml`，经 `services/model_config/registry.py` 读写。
- 语言 / 视觉已走 `get_language_client()` / `get_vision_client()` 的调用：文章评分、故事聚类、配图 VL、模型测试。
- 仍直接 `OpenAI()` + `.env` 的调用：成片文案、摘要高亮、相关配图搜索词、部分爬虫子路径。
- 现有只偶尔读 `response.usage.total_tokens`（合规重试），没有落库，也没有配置页。

## 方案对比

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A. 统一补全封装 + 本地事件表（推荐）** | 所有 `chat.completions.create` 经 `complete_chat()`，写入 SQLite，配置页聚合展示 | 数字准、与现有配置一致、不依赖厂商账单 API | 漏接的调用点不会进统计，需把旧客户端迁过去 |
| B. 厂商用量 API | 调 OpenAI/DeepSeek/DashScope 账单接口 | 与官方账单一致 | 各家协议不同；本地兼容网关经常没有账单 API；对不齐「本系统」用量 |
| C. tiktoken 本地估算 | 请求前按文本估 | 实现快 | 视觉图 token 估不准；和账单对不上 |

采用 **A**。视觉图 token 一般已计入厂商返回的 `prompt_tokens`，不必单独估图。

## 架构

```
调用方 (评分 / VL / 文案 / 测试)
        │
        ▼
complete_chat(client, *, kind, profile, task, **kwargs)
        │  chat.completions.create
        │  parse usage
        ▼
record_token_usage(...)  →  llm_token_usage_events (SQLite)
        ▲
GET /api/models/usage     query_token_usage(range)
        │
系统配置 → 用量统计 Tab
```

单元边界：

1. **`parse_usage`**：从响应取出 prompt/completion/total，缺省为 0。
2. **`record_token_usage`**：写一行事件；失败只打日志，不抛给业务。
3. **`complete_chat`**：调用 + 解析 + 记录；业务方只换这一处。
4. **`query_token_usage`**：按北京时间窗聚合。
5. **设置页 Tab**：只读展示 + 清空本机记录。

## 数据模型

表 `llm_token_usage_events`：

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | String(32) PK | uuid hex |
| `created_at` | DateTime | UTC naive，与现网其他表一致 |
| `kind` | String(16) | `language` / `vision` |
| `profile_id` | String(64) nullable | 配置里的 profile id；`.env` 回退为 `env_deepseek` |
| `provider` | String(32) | deepseek / openai / qwen / volcengine / env |
| `model` | String(128) | 实际请求的 model 名 |
| `task` | String(64) | 见任务字典 |
| `prompt_tokens` | Integer | |
| `completion_tokens` | Integer | |
| `total_tokens` | Integer | 优先 `usage.total_tokens`，否则 prompt+completion |
| `ok` | Integer | 1 成功（有响应）；失败调用不写行 |

索引：`(created_at)`、`(kind, created_at)`、`(model, created_at)`。

不预聚合日表。本机调用量小，查询时 `SUM` 即可。

**任务字典（`task`）**

| task | 来源 |
|---|---|
| `article_score` | `article_score_llm` |
| `story_cluster` | `story_cluster_llm` |
| `image_score` | `image_score_vl` |
| `content_gen` | 成片文案 / 合规 JSON 补全 |
| `highlights` | 摘要高亮词 |
| `related_image_query` | 相关配图搜索词 |
| `model_test` | 系统配置里的测试按钮 |
| `crawler_content` | 爬虫路由里的 LLM 文案 |

## 采集规则

- 只记 **成功返回** 且能读到 `usage` 的调用。无 `usage` 时记 0 token、仍记 1 次调用，避免静默丢次数。
- 失败（超时、4xx）不记。
- 合规/JSON 重试：每一次 `create` 各记一行。
- 测试语言模型/视觉模型也记，`task=model_test`。
- 记录失败不得打断主流程。

## API

挂在现有 `api/routes/model_config_routes.py`（`/api/models`）：

`GET /api/models/usage?range=today|7d|30d|all`

`range` 按 **Asia/Shanghai** 切窗。`created_at` 按 UTC 存，查询时换算。

响应：

```json
{
  "success": true,
  "range": "7d",
  "totals": {
    "calls": 120,
    "prompt_tokens": 80000,
    "completion_tokens": 20000,
    "total_tokens": 100000,
    "language_tokens": 70000,
    "vision_tokens": 30000
  },
  "by_model": [
    {
      "kind": "language",
      "profile_id": "deepseek_chat",
      "display_name": "DeepSeek Chat",
      "provider": "deepseek",
      "model": "deepseek-chat",
      "calls": 90,
      "prompt_tokens": 50000,
      "completion_tokens": 15000,
      "total_tokens": 65000
    }
  ],
  "by_task": [
    {"task": "image_score", "label": "配图评分", "calls": 40, "total_tokens": 30000}
  ]
}
```

`POST /api/models/usage/clear`  
清空事件表。本机统计，不设二次确认后端校验；前端按钮确认即可。

## UI

系统配置新 Tab：**用量统计**（`data-tab="usage"`）。

- 时间窗：今日 / 近 7 天 / 近 30 天 / 全部。
- 汇总卡片：总 token、语言 token、视觉 token、调用次数。
- 表 1：按模型（语言/视觉标签、展示名、model、次数、输入/输出/合计）。
- 表 2：按任务。
- 空态：「该时间范围内还没有用量记录。完成一次模型测试或资讯评分后会显示在这里。」
- 「清空统计」：确认后调 clear。
- 样式跟现有 `model_settings.css` Soft UI，不用新图表库。

## 错误与测试

- 封装层：无 usage → tokens=0；记录异常被吞。
- 查询：非法 `range` → 400。
- 测试：parse_usage；record + query 聚合；API 摘要；clear；`complete_chat` mock 客户端会写库。
- UI：与现网设置页一样靠手工点；API 用 TestClient 覆盖。

## 非目标

- 按厂商官方账单对账、人民币估价、按文章/任务 ID 下钻、Prometheus、跨机器汇总。
