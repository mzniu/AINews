# AINews 项目说明与协作指引（Instruction）

本文档面向 **人类开发者** 与 **AI 助手**，用于快速理解仓库真实结构、职责边界与扩展方式。若与旧文档冲突，以 **代码与本文** 为准。

---

## 1. 项目是什么

**AINews** 是一站式 **AI 资讯 → 抓取/编辑 → DeepSeek 总结 → 竖屏关键帧与视频合成** 的工具集，附带 **去水印、GIF、GitHub 项目视频** 等能力。

- **主入口**：`web_server.py` — FastAPI 应用，挂载静态资源与 `data/`，注册各业务路由。
- **默认端口**：`8080`（见 `web_server.py` 中 `uvicorn.run`；README 中若写 8000 以代码为准）。
- **前端**：`static/` 下原生 HTML（如 `index.html`、`video_editor3.html`、`github_video_maker.html`）。

---

## 2. 顶层目录结构（与代码一致）

| 路径 | 作用 |
|------|------|
| `web_server.py` | 应用装配：CORS、静态目录、`api.routes.*` 路由注册 |
| `api/routes/` | HTTP 路由层（按功能拆分，部分共用 `/api` 前缀） |
| `api/schemas/` | Pydantic 请求/响应模型 |
| `services/` | 业务服务：爬虫编排、视频、GitHub 流程、GIF、缩略图等 |
| `src/crawlers/` | 各站点爬虫与 `base.py` 基类 |
| `src/models/` | 文章等数据模型；GitHub 相关模型可能在 `src/models/github_models.py` 等 |
| `src/utils/` | 配置、解析器、日志等（与根目录 `utils/` 并存，改代码前确认引用路径） |
| `utils/` | 如 `video_utils.py` 等，常被路由或服务直接 import |
| `static/` | 前端页面、图片、音乐等资源 |
| `data/` | 运行时产出（抓取内容、视频、GitHub 项目等，通常不入库或部分 gitignore） |
| `scripts/` | 爬虫脚本、Mock 数据等辅助脚本 |
| `docs/` | 设计说明与功能文档（细分功能见各 md） |
| `logs/` | Loguru 日志输出目录（若存在） |

**注意**：不存在旧版说明里常见的独立目录 `processors/`、`generators/`、`config/sources.yaml` 等；以本仓库实际路径为准。

---

## 3. 路由与 API 一览

路由在 `web_server.py` 中按顺序 `include_router`。主要前缀如下。

### 3.1 页面与健康检查（`main_routes`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主站 HTML |
| GET | `/video-maker`、`/video-editor3`、`/github-video-maker` | 各功能页 |
| GET | `/health` | 健康检查 |
| GET | `/api/list-music-files` | 列出 `static/music` 下 MP3 |
| POST | `/upload-local-image` | 本地上传图片 |

### 3.2 资讯抓取与总结（`crawler_routes`，前缀 `/api`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/fetch-venturebeat` | VentureBeat 等抓取 |
| POST | `/api/fetch-url` | 通用 URL 抓取 |
| POST | `/api/generate-summary` | DeepSeek 生成标题/摘要/标签 |
| POST | `/api/generate-image` | 生成关键帧图片 |
| POST | `/api/process-image` | 图片效果处理 |

### 3.3 视频（`video_routes`，前缀 `/api`）

包含列表、缩略图、上传图片、合成视频、动画视频、用户自定义视频等；具体见 `api/routes/video_routes.py` 中 `@router` 装饰的方法。

### 3.4 去水印（`watermark_routes`，前缀 `/api`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/detect-watermark` | 水印检测 |
| POST | `/api/remove-watermark` | LaMa 去水印 |
| POST | `/api/replace-edited-image` | 替换编辑后的图 |

### 3.5 GIF（`gif_routes`，前缀 `/api/gif`）

处理 GIF、批量、分析、抽帧等（见 `gif_routes.py`）。

### 3.6 GitHub 项目视频（`github_routes`，前缀 `/api/github`）

项目处理、选图、生成文案/视频、静态资源读取等（见 `github_routes.py` 与 `services/github_*`）。

### 3.7 其他

- `video_text_routes`：`POST /api/add-text-to-video`（视频叠加文字等）。
- `manual_content_routes`：`POST /api/process-manual-content`（手动粘贴内容流程）。

完整列表以各文件内路由定义为准；联调可使用 **http://localhost:8080/docs**（若启用 OpenAPI）。

---

## 4. 环境与运行

1. **Python**：3.11+（见 README）。
2. **依赖**：`pip install -r requirements.txt`。
3. **Playwright**：需 `playwright install chromium`（用于需 JS 渲染的页面）。
4. **环境变量**：复制 `.env.example` 为 `.env`，至少配置 `DEEPSEEK_API_KEY`（及可选 `DEEPSEEK_BASE_URL`）。
5. **资源**：背景图 `static/imgs/bg.png`、音乐 `static/music/*.mp3`；可用 `create_default_bg.py` 生成默认背景。
6. **启动**：`python web_server.py`，浏览器访问 `http://localhost:8080`。

---

## 5. 扩展与修改约定

### 5.1 新增/调整爬虫

- 继承 `src/crawlers/base.py` 中的 `BaseCrawler`。
- 在 `crawler_routes` 或 `services/crawler_service.py` / `async_article_crawler.py` 中按现有模式接入，保持 `Article` 等模型一致。
- 遵守站点 robots 与合理频率；网络异常时项目内已有 Playwright/回退相关实践，可参考现有爬虫实现。

### 5.2 新增 HTTP 接口

- 在 `api/routes/` 新建或扩展现有 router，使用 `APIRouter(prefix=...)` 避免路径冲突。
- 在 `web_server.py` 中 `include_router`；复杂逻辑放在 `services/`，路由层只做参数校验与调用。

### 5.3 视频与图片

- 视频合成、时长、关键帧逻辑集中在 `utils/video_utils.py`、`services/video_service.py`、`services/video_embedding_service.py` 等；修改前阅读调用链，避免重复实现。

### 5.4 日志与编码

- 服务端常用 **loguru**；Windows 下 `web_server.py` 已对 stdout 做 UTF-8 处理，新增脚本时注意控制台编码。

---

## 6. 测试与脚本

- 根目录存在大量 `test_*.py`、`quick_*.py`、`debug_*.py`，用于单点验证爬虫、截图、视频等；**非统一 pytest 目录结构**，运行前阅读文件内说明。
- 爬虫批量任务可参考 `scripts/run_crawler.py`。

---

## 7. 文档索引（`docs/`）

| 文档 | 内容方向 |
|------|----------|
| `01-项目概述.md` ~ `07-实施计划.md` | 背景、架构、爬虫、DeepSeek、视频、技术栈、计划 |
| `爬虫模块使用说明.md`、`爬虫网络问题解决方案.md` | 爬虫使用与排错 |
| `手动内容处理功能说明.md`、`图片编辑功能说明.md`、`视频生成功能说明.md` 等 | 各功能细节 |
| `摘要滚动显示功能说明.md` | 摘要滚动相关行为说明 |

设计文档中的 **数据库/Redis/定时任务** 等可能为规划项，实现以代码为准。

---

## 8. 其他协作文档

- **`.github/copilot-instructions.md`**：Copilot 补充约定；文首已引用本文 **`INSTRUCTION.md`**。其中部分历史路径示意可能仍过时，**结构、API、端口以本文与源码为准**。

---

## 9. 修改代码时的原则（给 AI 助手）

- 只改任务所需文件，避免无关重构与大面积格式化。
- 新代码风格与周边文件一致（导入顺序、日志、异常处理方式）。
- 用户未要求时，不主动新增大段说明性 Markdown；本文件为项目级 instruction 例外。

---

*文档生成依据：仓库目录、`web_server.py`、`api/routes/*.py`、`README.md`、`.env.example`。若接口或端口变更，请同步更新本节与表格。*
