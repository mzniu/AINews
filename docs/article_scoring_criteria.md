# 快讯向文章选题评分标准（规则 + LLM 评语）

## 定位

面向 **AI 快讯** 自媒体：优先时效、名企名人、产品热点与传播钩子，不追求深度长文。

## 评分结构

- **规则分**：0–100，入库时自动计算（无 LLM 成本）
- **LLM 评语**：可选，生成快讯判断、标题角度、风险点（需配置 `DEEPSEEK_API_KEY`）

## 维度与权重（快讯 profile）

| 维度 | 权重 | 说明 |
|------|------|------|
| 时效性 | 20% | 24h 内满分，逐档递减 |
| 显著性 | 18% | 名企、名人、二线公司 |
| 突破性 | 18% | 首发/开源/SOTA/融资等信号词 + 关键数字 |
| 产品热度 | 15% | ChatGPT、Kimi、DeepSeek 等热词 |
| 传播钩子 | 12% | 标题数字、反差词、疑问句 |
| 话题相关 | 10% | 与 AI 垂类关键词匹配 |
| 数据信号 | 5% | 浏览量、同题多篇 |
| 可创作性 | 2% | 摘要/配图数量（≥3 张满分加成） |

## 扣分项

| 情形 | 默认扣分 | 说明 |
|------|----------|------|
| 配图不足 | -6 | 本地成功下载配图 **少于 3 张** |
| 营销稿特征 | -8 | 命中多个营销词 |

## 等级

| 等级 | 分数 | 建议 |
|------|------|------|
| S | ≥85 | 立即出快讯 |
| A | 70–84 | 今日优先 |
| B | 55–69 | 简讯/合集 |
| C | 40–54 | 观察归档 |
| D | <40 | 不建议跟进 |

## 配置

词表与权重见 `config/article_scoring.yaml`，可按账号调优。

## 自动流程（抓取后）

1. **入库瞬间**：规则引擎打分并定级（所有文章）
2. **S/A 级**：自动调用 LLM 生成评语，并可修正等级/分数（需 `DEEPSEEK_API_KEY`）
3. **S 级**（`post_score_automation`）：自动执行：
   - 配图相关度评估（视觉模型）
   - AI 标题/摘要/口播稿生成（写入 `video_draft_json`）
   - `prepare-video` 生成主页导入元数据（含自动勾选配图）
4. 最终结果写入 `score_grade` / `score_total`；主页素材就绪后 `video_prep_at` 有值，资讯库显示「主页就绪」

配置见 `config/article_scoring.yaml` → `post_score_automation`。

## API

- `POST /api/ingestion/articles/{id}/score` — body: `{ "use_llm": true }`
- `POST /api/ingestion/articles/score-batch` — 批量规则评分
- `GET /api/ingestion/articles?sort=score_desc` — 按分排序

## 脚本

```bash
python scripts/backfill_article_scores.py
python scripts/backfill_article_scores.py --source aitnt_travel --use-llm
```
