# 候选池管理页面设计

## 目标
为运营人员提供可分页、可筛选、可操作的候选池页面，解决「候选只显示数量、无法单条处理」的问题。

## 核心决策
- 新增独立页面 `/candidate-pool`，左侧导航「分发」分组下新增入口。
- 后端复用 `AutoPublishCandidate` 模型，新增 `GET /candidates` 分页列表与两个动作接口。
- 跳过动作将候选状态置为 `skipped`；立即入队调用现有调度逻辑生成 `PublishJob`。

## 数据模型
已有 `src/db/models/publishing.py::AutoPublishCandidate`：

- `id`: 主键
- `article_id`: 关联文章
- `platform`: `douyin` / `kuaishou` / `wechat_channels`
- `action`: 当前动作（`publish` / `defer` / `skip`）
- `recommended_action`: 策略推荐动作
- `priority`: 优先级分数
- `reasons_json`: 策略原因数组
- `policy_version`: 策略版本
- `status`: `pending` / `deferred` / `skipped` / `dispatched`
- `evaluated_at`: 评估时间
- `scheduled_date`: 已调度日期
- `publish_job_id`: 关联 PublishJob（dispatched 后）

## API

### GET /candidates
参数（query）：
- `page` (int, default=1)
- `per_page` (int, default=20)
- `platform` (str, optional): `douyin`, `kuaishou`, `wechat_channels`
- `status` (str, optional): `pending`, `deferred`, `skipped`, `dispatched`
- `recommended_action` (str, optional): `publish`, `defer`, `skip`
- `sort_by` (str, default=`priority`): `priority`, `evaluated_at`, `created_at`

返回：
```json
{
  "success": true,
  "total": 120,
  "page": 1,
  "per_page": 20,
  "items": [
    {
      "id": "...",
      "article_id": "...",
      "title": "文章标题",
      "platform": "douyin",
      "action": "publish",
      "recommended_action": "publish",
      "priority": 82.5,
      "reasons": ["recommend.publish.douyin_grade_threshold", "priority.platform_fit"],
      "status": "pending",
      "evaluated_at": "...",
      "created_at": "..."
    }
  ]
}
```

### POST /candidates/{candidate_id}/skip
效果：将 `AutoPublishCandidate` 状态置为 `skipped`（幂等）。
返回：
```json
{ "success": true, "candidate_id": "...", "status": "skipped" }
```

### POST /candidates/{candidate_id}/enqueue
效果：
1. 校验候选为 `pending` 或 `deferred`。
2. 调用 `services.publishing.candidate_queue._dispatch_one_candidate`（新增）生成 `PublishJob`。
3. 更新候选状态为 `dispatched` 并关联 `publish_job_id`。

返回：
```json
{ "success": true, "candidate_id": "...", "status": "dispatched", "publish_job_id": "..." }
```

## 页面结构
路径：`/candidate-pool` 对应 `static/candidate_pool.html`。

页面元素：
- 标题栏：候选池 + 刷新按钮
- 筛选器：平台、状态、推荐动作、排序
- 分页表格：标题、平台、推荐动作、状态、优先级、原因、操作
- 操作按钮（每行）：跳过、立即入队

## 交互
- 首次进入加载第 1 页。
- 筛选器变更后重新加载第 1 页。
- 跳过/立即入队操作成功后刷新当前页。
- 操作失败显示 toast 提示。

## 样式
复用 `static/css/app_shell.css` 左侧导航。
新建 `static/css/candidate_pool.css` 处理表格与筛选器布局，风格与 `publish_queue.css` 保持一致。

## 文件变更
- `api/routes/publishing_routes.py`: 新增 `/candidates` 与动作接口。
- `services/publishing/candidate_queue.py`: 新增 `_dispatch_one_candidate`。
- `static/candidate_pool.html`: 新增页面。
- `static/css/candidate_pool.css`: 新增样式。
- `static/js/candidate_pool.js`: 新增交互。
- `static/js/shared/app_nav.js`: 导航新增「候选池」入口。
- `static/publish_center.html`: 发布中心保留候选数量卡片，加链接到候选池。

## 测试
- `tests/test_candidate_pool.py`: 新增接口测试。
