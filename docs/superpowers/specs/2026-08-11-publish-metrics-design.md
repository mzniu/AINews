# 发布内容跨平台数据看板设计

> 日期：2026-08-11  
> 状态：已批准实施（历史数据策略 A：模糊匹配 + 待匹配）

## 目标

在发布中心查看已发布作品在各平台的表现数据，每日自动更新一次。

## 核心决策

- **采集方式**：创作者中心 Playwright 抓取（与现有发布架构一致）
- **历史数据**：仅对能 ID/模糊匹配上的回填；其余标记 `unmatched`
- **实施顺序**：P0 数据模型 → P1 小红书 → P2 抖音/快手/视频号 → API/UI

## 数据模型

- `publish_jobs` 扩展：`platform_post_url`, `metrics_match_status`, `metrics_last_synced_at`
- `publish_post_metric_snapshots`：每日指标快照（唯一约束 job_id + snapshot_date）
- `publish_metrics_sync_runs`：同步任务审计

## 定时任务

Publish Worker APScheduler：`0 6 * * *` Asia/Shanghai，账号串行，与发布任务互斥 browser lock。

## API

- `GET /api/publishing/published-posts`
- `GET /api/publishing/published-posts/{job_id}/metrics`
- `GET /api/publishing/metrics/summary`
- `GET /api/publishing/metrics/sync-status`
- `POST /api/publishing/metrics/sync`
