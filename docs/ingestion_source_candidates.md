# 资讯入库备选源验证清单

> 自动生成于 2026-08-01 00:46:21 +0800，由 `scripts/probe_ingestion_candidates.py` 产出。

## 已接入

| ID | 名称 | 列表 URL | 状态 | 详情字数 | 图片 |
|---|---|---|---|---:|---:|
| `aitnt_travel` | AITNT Travel | http://travel.aitntnews.com/?index=1 | pass | 3390 | 41 |
| `kr36_ai` | 36氪 AI | https://www.36kr.com/information/AI/ | pass | 2123 | 6 |
| `qbitai` | 量子位 | https://www.qbitai.com/ | pass | 2212 | 10 |
| `leiphone_ai` | 雷锋网 AI | https://www.leiphone.com/category/ai | pass | 4086 | 15 |

## 备选（待接入）

| 推荐度 | ID | 名称 | 列表链接数 | 详情字数 | Playwright | 代理 | 说明 |
|---|---|---|---:|---:|---|---|---|
| 需 Playwright / 反爬 | `jiqizhixin` | 机器之心 | 0 | 0 | 是 | 是 | 页面过短(3251B)，疑似反爬 |
| 推荐接入 | `leiphone_ai` | 雷锋网 AI | 28 | 4086 | 否 | 否 |  |
| 需 Playwright / 反爬 | `huxiu_ai` | 虎嗅 AI | 0 | 0 | 是 | 否 |  |
| 需进一步 Spike | `geekpark` | 极客公园 | 20 | 0 | 是 | 否 |  |
| 推荐接入 | `aitnt_tech` | AITNT Tech | 1 | 3390 | 否 | 否 | 与 travel 同结构，建议复用 aitnt_news |
| 需 Playwright / 反爬 | `venturebeat_ai` | VentureBeat AI | 0 | 0 | 是 | 否 | 英文源 |

## 接入优先级建议

1. **雷锋网 AI** / **虎嗅 AI** — 静态 HTML 概率高，中文 AI 垂直
2. **AITNT 其他子站** — 复用 `aitnt_news` 适配器即可
3. **极客公园** — 需 Spike 确认列表结构
4. **机器之心** — 需代理或 Playwright
5. **VentureBeat** — 英文源，按需接入
