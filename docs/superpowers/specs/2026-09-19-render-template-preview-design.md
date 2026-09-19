# 成片模板预览

> 日期：2026-09-19  
> 状态：已批准实施  
> 范围：设置页 YAML 编辑器旁封面自动预览 + 短视频按钮预览

## 目标

改 YAML 时能看到真实渲染效果，不必先保存、也不必出一篇资讯。

## 行为

- 左 YAML，右预览。
- 封面：加载模板后立即渲一张；之后 textarea 停顿 1 秒再渲。非法 YAML 报错并保留上一张图。
- 短视频：点「预览短视频」才渲，约 1 张样例图、约 3 秒，Python/moviepy（含 Ken Burns / 打字机）。
- 预览读取 textarea 原文，**不写** `config/render_templates.local.yaml`。
- 样例文案固定；配图用模板 `background_image` 或仓库样例图。

## 接口

- `POST /api/ingestion/render-templates/preview-cover` `{ yaml }` → `{ success, image_url }`
- `POST /api/ingestion/render-templates/preview-video` `{ yaml }` → `{ success, video_url }`
- 非法 YAML / 未知 layout_kind → 400

封面走 `render_article_cover`；短视频走 `render_ingested_video(..., renderer="python")` 并压低 `min_duration_sec`。产物在 `data/cache/template-preview/`，经 `/data/...` 提供。
