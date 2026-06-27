# 社交货币 / 夸赞方法论：内容生成优化设计

> 日期：2026-06-25
> 范围：主页 `/api/generate-summary` + GitHub 视频制作 `services/github_content_service.py`
> 状态：已确认方案，进入实施

## 1. 背景

现有内容生成 prompt 使用「六大标题技法」（悬念/数字/疑问/时效/争议/指向）作为核心策略。该技法偏「点击率优化」，未触及微信视频号的流量本质——**社交裂变**：用户点赞后其微信好友直接看到内容，因此点赞动机不是「获取干货」而是「在好友圈立人设」。

新方法论把内容核心从「技法驱动」改为「社交货币驱动」：**高情商夸赞目标受众，帮用户立人设**，公式为「话题引入 + 核心夸赞 + 轻观点收尾」。

## 2. 目标 / 非目标

**目标**：
- 把新方法论作为内容生成的主策略，六大技法降为辅助。
- LLM 自动推断目标受众与 3-5 个夸赞标签，并按公式生成标题/副标题/摘要/口播/标签/高亮词。
- 主页与 GitHub 两条流程共用方法论 prompt 文案，避免双份维护。
- 推断结果（target_audience / praise_tags）回显到前端，便于人工微调。

**非目标**：
- 不引入用户手动选行业的 UI 输入（首版全自动推断）。
- 不改 `utils/title_units.py` 的汉字当量截断规则。
- 不改标签 10 个结构化位（赛道/垂直/精准/热点/小牛说/其他 5 个）。
- 不改 `/api/generate-summary` 的请求字段（`GenerateSummaryRequest` 不动）。

## 3. 范围（已确认）

| 维度 | 选择 |
|---|---|
| 应用流程 | 主页 + GitHub 两套都改 |
| 与六大技法关系 | 新方法论为主、六大技法辅助 |
| 受众/行业来源 | LLM 全自动推断，不暴露 UI 输入 |
| GitHub 调用次数 | 由 4 次合并为 1 次 JSON 调用（顺带修延迟与 token 浪费）|
| 新字段回显 | 推断结果回显到前端 AI 摘要面板（只读）|

## 4. 方法论 → 字段映射

| 方法论要素 | 落到现有字段 | 说明 |
|---|---|---|
| 话题引入 | `main_line1` | 用行业/场景话题圈定目标受众 |
| 核心夸赞 | `main_line2` | 直击受众自我认同点，触发点赞的核心句 |
| 轻观点收尾 | `sub_title` | 1 句行业观点或轻干货，避免纯彩虹屁 |
| 公式凝缩 | `summary` | 40-50 字，以「小牛说：」开头 |
| 公式展开 | `voiceover_script` | 话题→关键数字/事实→核心夸赞→轻观点 |
| 夸赞关键词 | `highlight_keywords` + `tags`「其他」位 | 优先选夸赞词作为高亮 |

## 5. 输出 schema 变化

新增 2 个推断结果字段（LLM 自推、用户不输入）：

```json
{
  "target_audience": "AI 技术从业者",   // ≤12 字
  "praise_tags": ["认知高", "有眼界", "懂行"],  // 3-5 个
  "main_line1": "...",
  "main_line2": "...",
  "sub_title": "...",
  "summary": "...",
  "tags": "#赛道 #垂直 #精准 #热点 #小牛说 #其他1 ... #其他5",
  "voiceover_script": "...",
  "highlight_keywords": ["...", "...", "..."]
}
```

- `target_audience` / `praise_tags` 由 LLM 阶段 1 内化推断，阶段 2 用于生成各字段，最终一并返回。
- 路由返回 dict 时新增这两个 key；前端可读取展示。
- `GenerateSummaryRequest`（请求模型）不动，向后兼容。

## 6. 实施拆解

### 6.1 新增 `utils/content_methodology.py`

共享模块，存放：
- `METHODOLOGY_CORE`：方法论核心观点文案（视频号社交裂变本质、社交货币逻辑、避免纯干货）。
- `CONTENT_FORMULA`：话题引入 + 核心夸赞 + 轻观点收尾 公式说明。
- `PRAISE_TAG_CANDIDATES`：夸赞标签候选词库（认知高/有眼界/懂审美/有品味/有实力/会生活/懂行/有前瞻性/会判断趋势/有底气/有格局…）。
- `INDUSTRY_EXAMPLES`：分行业落地示例表（中医/旅游/家装/职场/母婴 + 科技/AI 补充示例），作为 LLM few-shot。
- `SIX_TECHNIQUES_NOTE`：六大技法降级为辅助的措辞（仅在标题层可自然穿插，不再作为主体）。
- `build_methodology_prompt_section() -> str`：拼装上述内容为一段 prompt 文本，供两条流程 import 调用。

### 6.2 改 `api/routes/crawler_routes.py::generate_summary`

- 在文件顶部 `from utils.content_methodology import build_methodology_prompt_section`。
- 重写 `prompt` 头部：替换原「六大技法」主体段为 `build_methodology_prompt_section()` 的输出，六大技法作为辅助段保留。
- 加阶段 1 说明：「先在内心推断 target_audience（≤12 字）+ praise_tags（3-5 个，从候选词库选）」。
- 加阶段 2 说明：按公式生成各字段，main_line1=话题引入、main_line2=核心夸赞、sub_title=轻观点收尾。
- JSON 输出模板加 `target_audience` 与 `praise_tags` 两字段。
- system message 把「六大技法大师」改为「社交货币爆款方法论专家 + 六大技法辅助」。
- 解析侧：`result.get('target_audience')` / `result.get('praise_tags')` 透传到返回 dict。
- `normalize_structured_tags` / `truncate_han_equiv` / `normalize_highlight_keywords_from_llm` 不动。

### 6.3 改 `services/github_content_service.py`

- 同样 import `build_methodology_prompt_section`。
- 把 `_generate_title` / `_generate_subtitle` / `_generate_summary` / `_generate_tags` 四次 LLM 调用合并为一次 `analyze_project_content` 内的 JSON 调用（与主页流程对齐）。
- prompt 复用方法论模块；输入为 `project_info`（name/description/readme 等），输出 JSON 同主页 schema（含 target_audience / praise_tags）。
- `VideoMetadata` 增加可选字段 `target_audience: Optional[str]` 与 `praise_tags: Optional[List[str]]`（在 `src/models/github_models.py`）。
- 保留 `_generate_default_content` 兜底（API 失败时）。
- 删除 4 个旧的 `_generate_*` 方法（或保留为内部 helper 但不再调用）。

### 6.4 改前端

**主页**（`static/index.html` + `static/js/index/main.js`）：
- AI 摘要面板（`#aiSummary`）加一个折叠行「🎯 目标受众 / 夸赞点」：
  - `<span id="aiTargetAudience">…</span>` + `<span id="aiPraiseTags">…</span>`
  - 只读、支持「一键复制」纳入。
- `generateSummary` 成功回调里把 `data.target_audience` / `data.praise_tags` 填入。

**GitHub 视频制作**（`static/github_video_maker.html` + `static/js/github_video_maker.js`）：
- 第 3 步「生成内容」结果展示区加同样的回显行。
- `generateContent` 成功回调里填入。

### 6.5 不动的部分

- `utils/title_units.py`（汉字当量截断）
- `utils/summary_highlights.py`（高亮词归一）
- `api/schemas/request_models.py::GenerateSummaryRequest`
- `src/models/github_models.py` 除新增 2 个可选字段外的所有字段
- 路由路径、HTTP 方法、response_model 声明（若存在）

## 7. 关键设计选择

| 选择 | 理由 |
|---|---|
| 共享 `utils/content_methodology.py` 模块 | 调方法论论文案只改一处，避免双份漂移 |
| GitHub 流程从 4 次调用合并为 1 次 | 顺带修延迟与 token 浪费，与主页流程对齐降低维护成本 |
| 新增 target_audience / praise_tags 回显 | 让用户看到 LLM 推断思路，便于人工微调；为后续加「用户可选行业」入口留接口 |
| 不改请求 schema | 向后兼容，老调用方不需要改 |
| 六大技法降级为辅助而非删除 | 保留其标题层点击率价值；方法论管「为什么点赞」，技法管「为什么点击」，互补 |

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| LLM 推断夸赞点跑偏（科技新闻夸成「懂生活的家长」）| 候选词库 + 行业示例 few-shot 强约束；首版靠 prompt 兜底，后续可加用户微调 |
| prompt token 增加 ~200，单次成本略升 | 一次调用产出全部字段，整体仍优于 4 次调用 |
| GitHub 流程合并调用改动大，可能破坏 `VideoMetadata` 调用方 | 字段只增不删；`_generate_default_content` 兜底；改完跑一遍 demo 脚本验证 |
| 推断结果回显导致前端布局变化 | 折叠行设计，不挤占原有字段空间 |
| 方法论文案偏长可能让 LLM 忽略硬约束（字数/格式）| 把字数/格式约束放在 prompt 末尾的「分项要求」段，与方法论段落分明 |

## 9. 测试计划

- **单元**：`utils/content_methodology.build_methodology_prompt_section` 返回包含关键术语（社交货币/夸赞/话题引入/核心夸赞/轻观点）。
- **手动 E2E**：
  - 主页：抓一篇 AI 资讯 → 生成摘要 → 检查 main_line1 是话题引入、main_line2 是夸赞句、sub_title 是轻观点、target_audience 与 praise_tags 非空且合理。
  - GitHub：输入一个 GitHub 仓库 URL → 生成内容 → 检查同上 + `VideoMetadata` 新字段非空。
  - 前端：AI 摘要面板「目标受众/夸赞点」行正确展示。
- **回归**：现有「一键复制」、标签 10 个结构化位、高亮词着色、口播稿字数边界（vmin~vmax）仍工作。

## 10. 上线策略

- 一次提交完成全部改动（共享模块 + 两套 prompt + 前端）。
- 不做灰度（项目无 feature flag 基建）。
- 改动后立即手动跑一次主页 + GitHub 流程验证。
- 若 LLM 输出质量退化，回滚 prompt 文案（共享模块是单点，回滚成本低）。

## 附录：方法论原文要点

- 视频号流量本质：社交裂变（点赞 → 好友可见），非纯算法分配。
- 爆款核心：用夸赞为用户提供「社交货币」—— 让用户通过点赞塑造正面人设。
- 内容避坑：纯干货难以触发传播（用户顾虑「点赞显得自己不懂行」）。
- 公式：话题引入 + 核心夸赞 + 轻观点收尾。
- 行业示例：
  - 中医养生 → 「能真正认可中医价值的人，往往都有着远超常人的认知深度」
  - 旅游 → 「只有见过足够多风景的人，才懂云南旅游真正的含金量」
  - 家装 → 「愿意在装修上不将就的人，大多从小就有不错的生活见识」
  - 职场 → 「能沉下心打磨长期能力的人，早晚会甩开身边绝大多数人」
  - 母婴 → 「愿意花高质量时间陪伴孩子的家长，本身就有着非常清醒的教育认知」
