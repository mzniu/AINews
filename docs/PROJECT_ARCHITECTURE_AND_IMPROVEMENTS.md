# AINews 项目架构与改进建议

> 本文由并行子代理（API/Web 层、Services 业务层、视频生成管线、数字人/TTS、GitHub 视频管线、前端 UX、仓库卫生与运维）分别审计后汇总，时间为 2026-06-25。审计基线 = master 分支 `739a7eb`（feat: 使用 AINews 本地 IndexTTS 运行时）。
>
> 项目定位：一站式 AI 资讯处理工具——抓取网页/GitHub → DeepSeek 总结 → 自动生成竖屏短视频，并扩展到数字人口型同步与 TTS 配音。

---

## 0. TL;DR（最高优先级改进）

| # | 项 | 类别 | 影响 |
|---|---|---|---|
| 1 | 删除 `app.py` / `server.py` / `web_server_backup.py` 三个死入口 | 仓库卫生 | 入口识别混淆 |
| 2 | 清理根目录 50+ `test_*.py` / `debug_*.py` / `quick_*.py` 调试产物与 `=6.1.10` / `pkg_resources.py` / `xtcocotools/` 异常文件 | 仓库卫生 | 仓库根污染 |
| 3 | `.gitignore` 补齐 `models/`、`third_party/`、`test_outputs/`、`downloaded_images/`、调试媒体/HTML/JSON | 仓库卫生 | 防止大文件入库 |
| 4 | 收敛 CORS：禁用 `allow_credentials=True` 或改白名单 | 安全 | 凭证泄露 |
| 5 | `/replace-edited-image` 套 Pydantic 模型 + 路径白名单（限 `data/`） | 安全 | 任意文件覆盖 |
| 6 | Wav2Lip `torch.load` 加 `weights_only=True`；权重下载加 SHA256 校验 | 安全 | 反序列化 RCE / 供应链 |
| 7 | 把硬编码绝对路径（`C:\Users\Mingzhu`、`D:\BaiduNetdiskDownload\MetaHuman-2`）改为 env var + 项目相对路径 | 可移植性 | 换机即坏 |
| 8 | 合并 `github_screenshot_service` 与 `selenium_screenshot_service`；退役 `src/crawlers/` 死代码 | 重复实现 | 维护成本 |
| 9 | `video_routes.py` 1314 行拆分；`main.js` 2888 行拆分为 ES module | 可维护性 | 改动易漏 |
| 10 | 中间产物 TTL（`data/generated/anim_*`、`data/uploaded/`）+ 任务态落 SQLite + GPU 信号量 | 稳定性 | 磁盘膨胀 / OOM / 失忆 |

---

## 1. 总体架构

```
                ┌─────────────────────────────────────────────────────┐
                │  web_server.py  (FastAPI + uvicorn, /static, /data) │
                │  路由: crawler / github / video / watermark /         │
                │        main / digital_human / pip / manual_content   │
                └───────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼────────────────────────────┐
        ▼                       ▼                            ▼
  CrawlerService         GitHubProcessingService      VideoService /
  (Playwright+BS4)       (parser+image+screenshot     video_routes
        │                +content+storage)                 │
        ▼                       │                            ▼
  DeepSeek 总结              video_routes            _create_animated_video_blocking
        │                  .create_animated_video    (MoviePy 2.x + PIL 逐帧)
        ▼                       │                            │
  关键帧 → 合成视频       github_voiceover_service     └─→ data/videos/*.mp4
                         (IndexTTS + ASS + ffmpeg)
                                  │
                                  ▼
                          DigitalHumanService ── LipSyncEngineManager
                          (subprocess + conda)    (EchoMimic v2 → MuseTalk 1.5 → Wav2Lip)
```

### 1.1 入口

- **真正入口**：`web_server.py` —— uvicorn + `workers` env，挂载 `/static`、`/data`，注册 13 个 router。
- **死代码**：`app.py`（0 字节）、`server.py`（7 行测试桩）、`web_server_backup.py`（83 KB 旧副本，缺新路由）。

### 1.2 路由组织

| 路由文件 | 行数 | 主要端点 | 问题 |
|---|---|---|---|
| `video_routes.py` | 1314 | list / thumbnail / upload / create-video / create-animated-video / create-user-video | 单文件巨石，私有 helper 杂糅 |
| `main_routes.py` | - | HTML 页面 + 字体/音乐/底图 + upload + render-voiceover | 页面与 API 混杂 |
| `crawler_routes.py` | - | /api/fetch、generate-image、generate-summary | `generate-image` 实调 `VideoService`，名实不符 |
| `github_routes.py` | - | /api/github/process-project → images → content → video → voiceover | 端到端 5 步，与 voiceover 逻辑重复 |
| `digital_human_routes.py` | - | /api/digital-human/* | 任务态仅内存 |
| `pip_routes.py` | - | /api/pip-compose | 装饰器硬写前缀 |
| `watermark_routes.py` | - | /api/remove-watermark | 全局 monkey-patch `torch.jit.load`，非线程安全 |

前缀不统一：8 文件用 `/api`，`pip_routes` 与 `main_routes` 完全无前缀。

### 1.3 schemas / 配置

- `api/schemas/request_models.py`：Pydantic v2 + `Field` 校验完善。
- 契约一致性差：约 40 端点中仅 11 个声明 `response_model`；`manual_content_routes` 用 `data: Dict`、`replace-edited-image` 用 `request: dict`、`add-text-to-video` 用 `Form(JSON 字符串)` + `json.loads`、`create-user-video` 全 `Form`——四处绕过 Pydantic。
- 内联模型：`DigitalHumanGenerateRequest`、`PipComposeRequest` 定义在路由文件而非 `schemas/`。
- 配置三套并存：`src/utils/config.py::Config`、`web_server.py` 顶层 `load_dotenv()`、`crawler_routes` 内直接 `os.getenv("DEEPSEEK_API_KEY")`。`config/sources.yaml` 仅 `Config.load_sources` 读取且无路由使用。
- `.env` 含真实 DEEPSEEK/ARK key，已被 `.gitignore` 忽略，未泄露。

---

## 2. 各模块审计

### 2.1 API / Web 层

**关键问题**（按优先级）：
1. 死入口 `app.py` / `server.py` / `web_server_backup.py` 干扰识别。
2. CORS `allow_origins=["*"]` + `allow_credentials=True` 是无效且不安全的组合。
3. `/replace-edited-image` 接收 `dict` 任意路径，可覆盖/删除项目内任意文件（路径穿越）。
4. `video_routes.py` 1314 行、`main_routes.py` 页面与 API 混杂。
5. `github_service` 模块级懒加载单例无锁，首请求并发可重复实例化；`watermark_routes.get_lama_model` 全局 monkey-patch `torch.jit.load` 非线程安全。
6. 大量端点无 `response_model` 或用裸 `Dict`，OpenAPI 文档失真。

**改进建议**：
- **P0** 删除三个死入口；CORS 收敛为白名单并禁用 credentials 或改 `allow_credentials=False`；给 `/replace-edited-image` 套 Pydantic 模型 + 路径白名单（限 `data/`）。
- **P1** 拆分 `video_routes.py`：list / thumbnail / upload / create-* 各成子路由，helper 下沉 `services/video_service`；为 `manual_content`、`replace-edited-image`、`add-text-to-video`、`create-user-video` 补 Pydantic 请求模型与 `response_model`。
- **P1** `github_service` 改 `app.state` + `asyncio.Lock` 初始化；LaMa 模型在应用启动时一次性加载，去除运行时 monkey-patch。
- **P2** 统一前缀策略（全部 `/api/<resource>`），`main_routes` 拆为 `pages_routes` + `assets_routes`；路由层禁用 `os.getenv`，统一走 `Config`；`sources.yaml` 接入实际使用或移除。
- **P3** 内联模型迁入 `schemas/`。

**优点**：Pydantic v2 校验完善；`_resolve_background_image_path` 与 pip `_resolve_path` 已有路径穿越防护；阻塞的 ffmpeg/MoviePy 调用统一经 `asyncio.to_thread`；`digital_human_service` 用 `asyncio.Lock` 保护任务映射；上传有大小/类型限制；loguru 日志带 rotation；`.env` 已正确 gitignore；每个领域均有 `/health`。

### 2.2 Services 业务层

**服务清单与依赖**：
- `crawler_routes` → `CrawlerService`（Playwright + BS4 + requests 下载图片/视频）+ `async_article_crawler.AsyncVentureBeatCrawler`（aiohttp，仅 VentureBeat）。`CrawlerService` 内部还依赖 `video_thumbnail_service`（cv2 抽帧）。
- `github_routes` → `GitHubProcessingService` 聚合 `GitHubProjectParser` + `ImageManager` + `SyncGitHubScreenshotService` + `ContentAnalyzer` + `ProjectStorageManager`。
- `image_search_routes` → `image_search_scrape`（百度 acjson）。`related_image_routes` → `RelatedImageService`（DeepSeek 生词 → 百度/Bing/头条 → `CrawlerService.download_image`）。`cover_image_routes` → `seedance_image_service`（火山 Ark 文生图）。`video_routes` → `video_embedding_service`（cv2 画中画）。
- **`src/crawlers/` 全模块（BaseCrawler + 5 个子类）无任何路由或服务引用，仅被 test_*.py / scripts/run_crawler.py 引用——事实死代码。**

**重复 / 可合并**：
1. `github_screenshot_service`（Playwright）与 `selenium_screenshot_service`（Selenium）功能完全重叠，前者已在内部按 Python 版本/平台调用后者回退，二者还各自重复实现 `_highlight_stars_area` / `_hide_elements` / 字体缩放 / 浅色模式逻辑。
2. `async_article_crawler.AsyncVentureBeatCrawler` 与 `src/crawlers/venturebeat_crawler.py` + `universal_article_crawler.VentureBeatCrawler` 三份 VentureBeat 解析重复。
3. `CrawlerService.download_image` / `RelatedImageService` / `ImageManager` 各自实现 requests 下载 + 重试 + Referer 头。

**爬虫策略**：分层不清晰。实际线上仅两路：`CrawlerService.get_page_content`（Playwright 异步，每调用启停一次浏览器）与 `async_article_crawler`（aiohttp）。`src/crawlers/base.py` 的 Playwright/Selenium/requests 三态分支以及所有子类爬虫均未接入路由。`crawler_service.extract_content` 用大段 if/elif 按域名硬编码（qbitai/36kr/微信/头条），其中视频提取代码块（L250–279 与 L291–319）**完全重复粘贴**，`else` 分支与其他分支并列导致逻辑错乱（属 bug）。

**关键问题**（按优先级）：
1. **资源泄漏**：`CrawlerService.get_page_content`（L24–45）未用 `async with`，异常时 `browser.close()` 不执行，且每次请求都启停 Chromium，高并发下文件描述符/子进程累积。`src/crawlers/base._fetch_with_playwright/_fetch_with_selenium` 同样无 try/finally 保护。`video_thumbnail_service` 在异常路径不释放 `cv2.VideoCapture`。
2. **同步阻塞污染事件循环**：`crawler_routes.fetch_url` 直接 `await CrawlerService.get_page_content` 但其中 `extract_content` / `save_results` / `download_image` / `download_video` 全是同步 `requests.*` + `time.sleep` 重试，阻塞 ASGI worker。`RelatedImageService.collect_related_images` 同理。
3. **`async_article_crawler` 名不副实**：`_extract_*` 全是同步 BS4 操作却声明 `async`，`download_images` 中 `await asyncio.sleep(2)` 串行下载，无并发。
4. **`SyncGitHubProcessingService.process_project` 用 `asyncio.run` 包 already-async 服务**，若被 async 路由调用会爆「event loop running」。
5. **错误处理不一致**：重试策略散落各处——`download_image` 3 次指数退避、`download_video` 3 次线性、`ImageManager` 自定义、`async_article_crawler` 无重试、`seedance_image_service` 无重试。无统一 `RetryPolicy`。
6. **死代码**：`src/crawlers/` 全模块、`universal_article_crawler.py`、`crawler_service.extract_content` 重复视频块。

**改进建议**：
- **P0** 把 `CrawlerService` 的下载/解析改为 `asyncio.to_thread` 包装或全异步 `httpx`；为 `get_page_content` 加 `async with async_playwright()` + 复用浏览器单例。
- **P0** 合并 `github_screenshot_service` 与 `selenium_screenshot_service`，统一 `_highlight/_hide/font_scale` 逻辑。
- **P0** 删除 `src/crawlers/`（或迁移未死子类到 `services/crawlers/`），清理 `extract_content` 重复视频块与 `else` 分支 bug。
- **P1** 抽出 `HttpDownloader`（统一 UA/Referer/重试/PIL 校验）；定义 `RetryPolicy`（max_retries、退避、可重试异常白名单）注入各下载器与 LLM 调用；`async_article_crawler` 改真异步或并入 `CrawlerService`。
- **P2** `extract_content` 域名 if/elif 改为按 netloc 注册的 `Extractor` 策略表；`SyncGitHubProcessingService` 若无人调用则删除；`video_thumbnail_service` 加 `try/finally cap.release()`。

**优点**：`GitHubProcessingService` 通过 `asyncio.to_thread` 把同步重活外包线程池，模式正确；`SyncGitHubScreenshotService._run_playwright_in_thread` 用独立线程 + `asyncio.run` 解决嵌套事件循环；`github_image_service._download_file_via_github_api` 提供 raw.githubusercontent 不可达时的 API 回退；`github_service._prioritize_readme_images` 对 badge/shields 降权、对 raw 仓库素材升权排序合理；Windows + Python 3.13 下多级回退覆盖大量兼容性边缘情况。

### 2.3 视频生成管线

**主流程**：`POST /api/create-animated-video` 接 `CreateAnimatedVideoRequest` → `asyncio.to_thread(_create_animated_video_blocking)`：
1. `_resolve_background_image_path` 取底图（默认 `static/imgs/bg.png`）。
2. `_load_fonts`（按 key 在 cwd / static/fonts / Windows Fonts 查字体）。
3. `temp_draw` 预计算 `main_title_lines` / `sub_title_lines` / `summary_lines`。
4. 遍历 `processed_images`，按类型分支：GIF/动画 WebP 走 `gif_processor.extract_gif_frames` → `_render_frame_animated`；普通图走 `make_frame_func`（8 种 anim_type + zoom + scroll）；画中画走 `video_embedding_service.prepare_video_for_embedding` → `blend_video_into_background`。
5. 每段 `VideoClip(...).with_fps(24)`，`concatenate_videoclips` 拼成 `final_clip`；`AudioFileClip` → `with_speed_scaled(1.1)` → 不足则循环 → `subclipped(0, video_duration)` → `with_audio`。
6. `write_videofile` 输出到 `data/videos/animated_{timestamp}.mp4`，预览帧落 `data/generated/anim_{timestamp}/preview_*.png`。

`services/video_service.py::create_video_frames` 仅生成静态 PNG 关键帧，**不再参与成片主链路**，与 `_render_frame_animated` 各画一套标题/摘要样式，双份实现。

**MoviePy 2.x 使用**：基本正确（`from moviepy import VideoClip, concatenate_videoclips, AudioFileClip`、`with_fps()`、`with_audio()`、`with_speed_scaled()`、`subclipped()`）。残留：
- `services/gif_processor.py` 仍 `from moviepy.editor import ImageSequenceClip, VideoFileClip`（1.x 子模块路径，2.x 已无，try/except 静默降级，实际不可用）。
- `extract_video_thumbnail` 同时备 MoviePy 与 OpenCV 双路径，2.x 下 MoviePy 常失败。
- `final_clip.write_videofile` 未显式传 `threads` / `preset`，默认单线程 libx264。

**关键帧 / 字幕 / 时长规则**：README 写「1帧6秒 / 2帧3秒 / 3+帧首帧2.5s其余3s」，但 `_create_animated_video_blocking` **不再服务端强制**——`clip_duration = img_data['duration'] if img_data['duration'] is not None else DEFAULT_CLIP_DURATION`，`DEFAULT_CLIP_DURATION = 0.8+0.4+1.4 = 2.6s`（注释写 2.7，有 0.1s 偏差）。规则只在前端 `main.js` 传 `duration_per_frame: 2.5` 实现，服务端无校验。字幕由 `_render_frame_animated` 内逐帧 PIL 绘制（非 TextClip），高亮关键字经 `utils/summary_highlights.resolve_highlight_keywords` 分段着色。BGM 固定 1.1× 加速再循环裁齐。

**关键问题**（按优先级）：
1. **资源路径硬编码**：`static/imgs/bg.png`、`static/music/background.mp3`、`msyhbd.ttc` / `msyh.ttc` / `simhei.ttf` 散落 `services/video_service.py` / `video_routes.py` / `_load_fonts`。字体回退链依赖 `%WINDIR%/Fonts`，Linux/Docker 退到 `ImageFont.load_default()`（中文乱码）。相对路径 `Path("static/...")` 依赖 cwd，非项目根启动即失效。
2. **中间产物无清理**：`data/generated/anim_{timestamp}/`、`frames_{timestamp}/`、`user_{timestamp}/`、`preview_*.png` 全部保留；`data/uploaded/` UUID 文件永不删除；`gif_processor` 转换的 `_video.mp4` 临时片段未清。长期运行磁盘膨胀失控。
3. **MoviePy 1.x→2.x 残留**：`gif_processor.py` 导入在 2.x 环境 ImportError → `ImageSequenceClip=None` → `convert_gif_to_video` 永远返回 False，GIF→MP4 转换路径实际不可用（成片链路里 GIF 走的是 `_render_frame_animated` 逐帧 PIL，不依赖此函数，但 `process_gif_for_video` 便捷函数仍被外部引用即静默失败）。
4. **逐帧 PIL 渲染 + `VideoClip(make_frame)`**：每帧 `bg.copy()` + `ImageDraw` + `alpha_composite` + `np.array(bg)`，1080×1920 单帧约 30–80 ms，24fps×2.6s≈62 帧×N 段，全程单线程 CPU；`write_videofile` 默认单线程编码。`_apply_video_effect` 内 `gold_sparkle` 每帧重生成 60 粒子；摘要 `summary_scroll` 旧分支还有 `for x in range(bg.width): for y in range(bg.height): getpixel` 的 O(W×H) Python 双循环，极端慢。
5. **`services/video_service.py` 与 `utils/video_utils.py` 双套标题/摘要绘制**：`create_video_frames`（静态关键帧）的标题光晕/摘要渐变与 `_render_frame_animated` 各画一套，样式不一致且维护成本翻倍；前者生成的 PNG 实际未被成片主链路使用。
6. **重复字体加载**：`_load_fonts` 在每个请求内被多次调用；`create_video_frames` 内独立 `ImageFont.truetype("msyhbd.ttc", ...)` 不走 `_load_fonts`。

**改进建议**：
- **P0** 修 `gif_processor.py` 导入为 `from moviepy import ImageSequenceClip, VideoFileClip`，删 `moviepy.editor`；或整体退役该类，GIF 抽帧统一走 `_render_frame_animated`。
- **P0** 新增 `services/paths.py` 集中管理 `PROJECT_ROOT` / `STATIC_DIR` / `FONTS_DIR` / `BG_PATH` / `MUSIC_PATH`，全部用 `PROJECT_ROOT / "static" / ...`，字体查找跨平台用 `sys.platform` 分支（Linux 查 `/usr/share/fonts`、`~/.fonts`）。
- **P0** 中间产物 TTL：`anim_*` / `frames_*` / `user_*` 目录在视频写入成功后立即 `shutil.rmtree`；`data/uploaded/` 与 `data/videos/` 加保留上限（如 7 天/500 个），独立后台清理任务。
- **P1** 服务端兜底帧时长规则：在 `_create_animated_video_blocking` 内按 `len(processed_images)` 计算 fallback duration（1→6、2→3、3+→首 2.5 余 3），覆盖 `img_data['duration'] is None`。
- **P1** 性能：`write_videofile(..., threads=os.cpu_count(), preset='medium')`；`_apply_video_effect` 粒子位置按 `seed` 一次性预生成缓存；删除 `summary_scroll` 旧分支的逐像素 Python 双循环（改 `Image.blend` 或 `Image.alpha_composite`）。
- **P1** 并行：各片段帧渲染相互独立，可用 `concurrent.futures.ThreadPoolExecutor` 并行生成 `preview_raw` / `segment_frames`，最后再 `concatenate_videoclips`。
- **P2** 合并 `services/video_service.py` 的静态关键帧绘制与 `utils/video_utils._render_frame_animated` 为一套工具函数；`extract_video_thumbnail` 直接用 OpenCV，删 MoviePy 分支；修正 `DEFAULT_CLIP_DURATION` 注释 2.7 与实际 2.6 不一致。
- **P2** `video_routes.py` 抽 `services/animated_video_builder.py` 承载合成逻辑，路由层只做参数校验。

**优点**：`_safe_paste` 正确处理画面外裁剪；`title_units.py` 汉字当量截断（英文/数字计 0.5）是严谨的本地化长度控制；`_resolve_background_image_path` 对 `..` 与 `static/` 范围做了路径穿越防护；`scroll_up` 匀速模型物理直观且与图高解耦；摘要高亮（长词优先、`re.escape`、描边）实现完整；画中画 `PIP_SOURCE_DURATION_FACTOR=1.5` 的「读 1.5× 时长再压回 1×」快进策略巧妙，避免素材过短黑屏；`asyncio.to_thread` 让出事件循环。

### 2.4 数字人 / 口型同步 / TTS

**管线现状**：介于 demo 与生产之间。`DigitalHumanService` 提供 in-memory 任务字典、asyncio 调度、ffmpeg/MoviePy 兜底；`LipSyncEngineManager` 三档优先级 EchoMimic V2 > MuseTalk 1.5 > Wav2Lip，按 `is_available()` 探测。AI 推理全部以子进程 + 独立 conda Python 隔离，主进程不加载 torch。**但任务态无持久化、无并发上限、无超时（除 IndexTTS 1800s 外）、无显存预算，多任务并行会撞 GPU OOM。**

**第三方依赖**：
- EchoMimic V2：`antgroup/echomimic_v2`（实际用 `BadToBest/EchoMimicV2` HF 仓库），acc 推理脚本 `infer_acc.py`，fp16，steps=20，768×768，固定 seed=42。
- MuseTalk 1.5：`third_party/MuseTalk`（git clone），需 conda env `musetalk`（Py3.10 + torch2.0.1+cu118 + mmcv2.0.1 / mmdet3.1.0 / mmpose1.1.0）。
- Wav2Lip：`third_party/Wav2Lip` + `Wav2Lip_GAN.pth`（从 `hf-mirror.com/Nekochu/Wav2Lip` 下载，无校验）。
- IndexTTS：本地运行时 `data/indextts_runtime/tts-2`，优先 `kelong_tts2` 编译版，回退 `indextts.infer.IndexTTS`；声学参数 fp16 / cuda_kernel 受 env 控制。

**集成方式**：FastAPI 同进程注册路由 `/api/digital-human/*`；推理通过 `subprocess.Popen` 调独立 conda Python，stdout 行式读取更新进度。**无队列、无 Redis、无 worker pool，任务态仅在 `DigitalHumanService.tasks` 内存字典，进程重启即丢。** IndexTTS 同样走子进程，独立 `py312/python.exe` + 自定义 PATH/PYTHONHOME/HF_HOME。

**模型文件存储**：分散在 `third_party/<repo>/pretrained_weights` 与 `models/wav2lip/`；**硬编码绝对路径** `D:\BaiduNetdiskDownload\MetaHuman-2\...`、`C:\Users\Mingzhu\anaconda3`、`D:\git\AINews\AINews\...`。下载脚本走 HF mirror + ModelScope，多源回退，但 `download_wav2lip_model` 用 `urllib.request` 直拉无哈希校验，`snapshot_download` 也未做 SHA256 比对。

**GPU/显存调度**：无显存管理。`batch_size` 经验映射（MuseTalk `bs*8→32`，Wav2Lip `bs*16→128`）但无 OOM 重试；并发任务无 GPU 互斥锁，多用户并触发会爆显存。IndexTTS 通过 `INDEXTTS_CUDA_VISIBLE_DEVICES` 隔离但 lip_sync 无类似开关。

**失败回退**：引擎级回退链清晰（auto=EchoMimic→MuseTalk→Wav2Lip），可用性检测覆盖权重/ffmpeg/python；但 mode=ai 且所有引擎不可用时直接 500，**无「自动降级到 fast」逻辑**。Wav2Lip 加载时 `torch.load` 无 `weights_only=True`，存在反序列化 RCE 风险。

**安全**：上传仅校验扩展名+大小，无 magic bytes 校验；`_resolve_project_path` 限 data/static 但允许 `METAHUMAN_REFERENCE_DIR` 外引目录。权重加载无签名校验；子进程命令拼接路径但无 shell=True，相对安全。

**关键问题**（按优先级）：
1. 硬编码用户绝对路径（`C:\Users\Mingzhu`、`D:\BaiduNetdiskDownload`），换机即坏。
2. 任务态无持久化 + 无并发上限，生产环境易失忆/OOM。
3. Wav2Lip `torch.load` 无 `weights_only`，反序列化 RCE。
4. 下载无哈希校验，供应链风险。
5. 顶层散落 7 个调试/下载脚本污染仓库根。
6. EchoMimic 输出靠「最近修改时间 rglob `*_sig.mp4`」取文件，并发任务可能错拿。
7. 无 GPU 互斥/排队，多请求必撞。
8. IndexTTS 路径回退到 `BaiduNetdiskDownload` 的错误提示暴露内部路径。

**改进建议**：
- **P0** 把所有硬编码绝对路径改为 env var + 相对项目根，`setup_*.bat` 参数化；Wav2Lip `torch.load(..., weights_only=True)`；任务态落 SQLite + 进程级 GPU 信号量（一次仅 1 个 AI 任务）。
- **P0** 删除 `check_*` / `download_*` 顶层脚本，归并到 `scripts/setup/`；权重下载加 SHA256 校验文件。
- **P1** EchoMimic 输出用 `task_id` 命名目录而非全局 `output/`，杜绝并发错拿；mode=ai 全不可用时自动回退 fast 并告警。
- **P1** 引入 RQ/Celery 或 `asyncio.Queue` worker，任务持久化、可查询、可取消；进度改 SSE/WebSocket。
- **P2** 统一 `INDEXTTS_CUDA_VISIBLE_DEVICES` 模式到 lip_sync（`LIPSYNC_CUDA_VISIBLE_DEVICES`）；显存监控 + OOM 自动降 batch_size；上传加 magic bytes 校验；`METAHUMAN_REFERENCE_DIR` 路径白名单化；EchoMimic steps/cfg/batch_size 暴露到 API 参数；新增 `/health/lip-sync`。

**优点**：引擎三档回退 + `availability_reason()` 诊断信息详尽；子进程隔离独立 conda env，避免 torch/mmcv/transformers 版本污染主服务；`indextts_worker.py` 对 v1/v2 config 兼容性处理（剥离 GPT 无效 key）细致；ASS 字幕烧录算法（中英文混排、按字号换算像素、词边界回缩）成熟可复用；`_resolve_project_path` 路径白名单 + 上传大小限流到位；进度反馈粒度（ffmpeg `out_time_ms` 解析、子进程 stdout 行式回流）体验良好。

### 2.5 GitHub 视频管线

**端到端流程**：前端 `github_video_maker.html` 是 5 步向导。
1. 输入仓库 URL → `POST /api/github/process-project`。
2. `GET /projects/{id}/images` 拉素材列表 → `POST /select-images` 勾选图片/README 视频。
3. `POST /generate-content` 让 `ContentAnalyzer`（DeepSeek/OpenAI）生成标题/副标题/摘要/标签。
4. `POST /generate-video`：`GitHubProcessingService` → 调 `video_routes.create_animated_video`（即主管线）产出基底视频。
5. `POST /projects/{id}/voiceover` → `github_voiceover_service.render_voiceover_for_video`：IndexTTS 子进程合成语音 + SRT/ASS 字幕 + ffmpeg 混 BGM、烧录字幕。

**与主管线关系**：成片阶段直接复用 `video_routes`，未另起一套合成器——**这是正确的去重**。但 `github_voiceover_service.py`（967 行）自实现 SRT/ASS 分段（`_split_script_to_segments`、`_chunk_long_sentence_flexible`、`_ffmpeg_burn_subtitles`），与主管线字幕工具高度重叠，存在第二套字幕烧录实现。

**数据获取**：走 GitHub REST API（`/repos`、`/readme`、`/contents`、`/markdown`），raw 域失败时回退 Contents API + base64。Token 仅从 `GITHUB_TOKEN` env 读取，**未做 X-RateLimit 头检查、未处理 429、无指数退避**。镜像走 `utils/github_mirror.py` 两个 env 变量（`GITHUB_RAW_MIRROR_PREFIX`、`GITHUB_API_MIRROR`），设计干净。

**截图服务取舍**：`github_screenshot_service.py` 是 Playwright 主路径，`selenium_screenshot_service.py` 是 Python 3.13+ Windows 上的备胎。实际入口 `SyncGitHubScreenshotService.take_screenshot_sync` 按 Python 版本+平台分支：3.13/Win 先 Selenium 后 Playwright，其它先 Playwright 后 Selenium，二者都失败时默认返回 False（PIL 占位图由 `GITHUB_SCREENSHOT_ALLOW_FALLBACK=1` 才启用）。**分支逻辑过于复杂。**

**前端组织**：单文件巨石（`github_video_maker.js` 1260 行），无模块化、无框架，状态用顶层 `let`（`currentProjectId`、`imageCatalog` Map、`selectedImageItems`、`generatedContent`、`baseVideoPath`）。

**错误反馈链路**：后端 `logger.error` + `HTTPException(detail=str(e))`；前端 `showNotification(msg, 'error')` 覆盖全部按钮回调。链路完整但消息粒度粗（直接拼内部异常字符串），`get_project_video` 用 glob 兜底匹配视频，命中错误项目的风险高。

**关键问题**（按优先级）：
1. 无速率限制/重试，易被封。
2. 截图双引擎分支复杂、Selenium 与 Playwright 都需安装。
3. 字幕工具与主管线重复实现。
4. 前端 1260 行单文件难维护。
5. `get_project_video` 用 glob 反查不可靠。
6. `GitHubProcessingService` 重跑不增量、全量重下。
7. 错误 detail 泄露内部路径。

**改进建议**：
- **P0** 在 `GitHubAPIClient` 加 `X-RateLimit-Remaining` / `Retry-After` 感知 + 429 指数退避；Markdown HTML 渲染改本地（`markdown` 或 `mistune`）省一次 API 调用；`get_project_video` 改为在 `metadata.json` 中持久化 `video_path` 字段；前端 `github_video_maker.js` 拆分为 `state.js / api.js / steps/*.js` 模块。
- **P1** 截图服务收敛为单一引擎（保留 Playwright，Selenium 仅作环境变量显式启用），删除 PIL 占位图分支或抽到独立 util；`github_voiceover_service` 的字幕分段/烧录抽取到 `utils/subtitle_*` 与主管线共享；`process-project` 检测到本地 `metadata.json` 存在时走增量；错误返回改为 `{error_code, message, detail}` 结构化。
- **P2** Star History 改为直接拉 SVG + 本地 cairosvg/svglib 栅格化，避免依赖 star-history.com 与整页截图；`_prioritize_readme_images` 的低价值 host 列表抽到配置文件；`SyncGitHubProcessingService`（`asyncio.run` 包装）标注仅脚本使用，避免被 ASGI 调用。

**优点**：服务分层清晰（content / image / screenshot / storage / voiceover 各司其职）；`asyncio.to_thread` 隔离同步阻塞 IO；镜像 env 变量零侵入；`find_cached_project_id` 本地缓存探测避免重复下载；Star History 自动 PIL 裁白边；`GITHUB_SCREENSHOT_ALLOW_FALLBACK` 默认关；metadata.json 每项目一份可调试；README 图片优先级排序（项目截图 > raw 资产 > 徽章）效果合理。

### 2.6 前端 UX

**页面与共享**：多 HTML 多页面（index / video_maker / github_video_maker / digital_human），非 SPA。每个页面独立 `<link>` 自有 CSS，`<nav class="navbar">` 在 4 个 HTML 中逐字重复；`video_maker.html` 把整套 nav 样式内联进 `<style>`，与 `index.css` 重复。`index.html` 530 行内联大量 `style="..."`，与 `index.css` 大量重复。

**JS 组织**：原生 JS，无 ES module（全部 `<script src>` 顺序加载，依赖全局函数），无打包工具、无 package.json。index 拆 4 文件（state/main/modal/init）但 **`main.js` 2888 行**、`modal.js` 1055 行；函数全挂 window，`onclick` 内联 `fetchUrl()` / `generateSummary()` 等。`github_video_maker.js` 1260 行、`digital_human.js` 342 行（后者用了 `const state=`、`engineSeg.addEventListener`，结构最干净）。代码风格不统一：缩进 4/8 空格混用。

**API 交互**：全部 `fetch`（main.js 21 处、github 2 处），无 axios。错误处理分散：每处 `try/catch` 各自 `console.error` + `showToast`，**无统一拦截器 / 无状态码分支 / 无重试 / 无超时**。loading 用 `display:none` 切换 `#loading` 节点，**无按钮 disabled 防抖、无全局请求锁**；`onclick="fetchUrl()"` 可重复点击触发并发请求。仅 github 出现 2 次 setTimeout 轮询任务状态，无标准 polling 抽象。

**CSS/资源**：4 个 CSS 共 3288 行，**零设计 token、零 `:root` 变量、零 `@media`**。颜色 `#667eea` / `#764ba2` 在多处硬编码数十次。资源风险突出：`fonts/subtitle/ZiHunYanBoSon.ttf` **2.3 MB** 单文件，`imgs/bg.png` 3.5 MB + `bg - 副本.png` 3.5 MB（疑似冗余复制），music 目录 7 个 mp3 共约 15 MB（Daytime.mp3 5.5 MB、Memories.mp3 6.3 MB），均无压缩/分片/懒加载。

**可访问性 / 响应式 / i18n**：a11y 几乎缺失——全仓 `aria-*` / `role=` / `tabindex` 0 处，`alt=` 仅 2 处且多为空串；交互全靠 `onclick` 内联，键盘不可达；模态框无 focus trap、无 Esc 关闭、无 aria-modal。响应式 0 个 `@media`，固定 `max-width:1200px`，移动端横向溢出。i18n 完全硬编码中文文案 + emoji。

**关键问题**（按优先级）：
1. `main.js` 2888 行 + 内联 onclick，可维护性极差。
2. nav/style 在 4 个 HTML 复制粘贴，改一处易漏三处。
3. 零设计 token、零响应式、零 a11y。
4. 大字体 2.3 MB + 大图 3.5 MB×2 + 大 BGM 6.3 MB 未压缩，首屏阻塞。
5. fetch 无统一错误处理/防抖/重试，并发请求风险。

**改进建议**：
- **P0** 抽公共 `partials/nav.html` + `css/tokens.css`（`:root` 定义颜色/间距/字号变量），4 页面复用；移除 `video_maker.html` 内联 `<style>`。
- **P0** 拆分 `main.js` 为模块（按功能：`fetch/api.js`、`ui/toast.js`、`image-selector.js`、`voiceover.js`），引入原生 ES module + 轻量打包（esbuild），废除全局函数 + onclick。
- **P0** 建 `apiClient`（统一 baseURL、JSON 解析、错误 toast、loading 锁、按钮 disabled 防抖、失败重试 1 次）；长任务抽 `pollTask(taskId)` 公共函数。
- **P1** a11y 修复——button 替代 `<a onclick>`、模态加 focus trap + Esc + `aria-modal`、所有 `<img>` 补 `alt`、`<nav>` 加 `aria-label`。
- **P1** 响应式——增加 `@media (max-width:768px)` 断点，nav 折叠为汉堡，grid 列数自适应。
- **P1** 资源优化——`ZiHunYanBoSon.ttf` 转 woff2 + 子集化（应在 200 KB 内）；删除 `bg - 副本.png`；mp3 转 128 kbps 或流式分段加载；bg.png 转 webp。
- **P2** 文案抽 `i18n/zh.json`，HTML 用 `data-i18n` 键值绑定；统一 lint（Prettier + ESLint）+ pre-commit hook。

**优点**：`digital_human.js` 结构最现代（`const state` + 事件绑定 + 状态机式 `updateEngineUI`），可作为重构模板；toast/showToast 抽象已成型；index 把 state 单独拆出方向正确；step-indicator 多步骤向导 UX 模式实现清晰；BGM/字体列表均走后端 API 动态加载（`/api/list-music-files`、`/api/list-title-fonts`），有 fallback 兜底。

### 2.7 仓库卫生与运维

**根目录脚本分类**（约 60 个文件）：
- **可删（一次性调试产物）**：`test_36kr*.py`、`test_playwright_*.py`、`test_51cto.py`、`test_real_*.py`、`test_selenium_*.py`、`test_github_*integration.py`、`test_venturebeat_*.py`、`test_video_*.py`、`test_comprehensive_gif.py`、`debug_*.py`、`quick_*.py`、`analyze_venturebeat.py`、`find_working_sites.py`、`comprehensive_*.py`、`final_verification_test.py`、`check_website.py`、`create_test_gifs.py`、`generate_audio_tests.py`、`demo_github_video.py`、`crawl_venturebeat_article.py`、`standalone_venturebeat_crawler.py`、`fix_github_issues.py`、`fetch_url.py`、`test_screenshot.jpg`、`test_selenium_screenshot.jpg`、`debug_page_sample.html`、`51cto_debug.html`、`temp_favicon.txt`、`venturebeat_*.json`、`quick_analysis.json`、`web_server_backup.py`。
- **移入 scripts/（有价值工具）**：`configure_cuda.py`、`verify_cuda_setup.py`、`create_default_bg.py`、`download_echomimic_models.py`、`download_denoising_unet_acc.py`、`download_pose_encoder.py`、`setup_echomimic_env.bat`、`setup_musetalk_env.bat`、`check_musetalk_avail.py`、`check_pose_encoder.py`、`verify_musetalk_env.py`、`test_musetalk_e2e.py`。
- **保留在根**：`web_server.py`、`app.py`（应删）、`server.py`（应删）、`requirements.txt`、`.env.example`。

**异常文件**：
- `=6.1.10`：误用 `pip install edge-tts >=6.1.10`（无引号），shell 把 `>=6.1.10` 重定向成文件名，内容是 pip 安装日志——**直接删除**，并修正对应安装脚本。
- `pkg_resources.py`：因系统 setuptools 损坏为 MuseTalk/mmengine 写的兼容 shim，不应放在业务仓库根目录污染 import 命名空间；建议移入 `third_party/shims/` 或通过 `setup_musetalk_env.bat` 修复 setuptools 后删除。
- `xtcocotools/`：mmpose 依赖的 COCO 工具源码副本，本应随 `pip install xtcocotools` 安装，**不应入库**；删除并改为环境脚本中 `pip install xtcocotools`。

**依赖管理**：`requirements.txt` 仅用 `>=` 下限，未锁定上限/具体版本，无 `requirements.lock` / `pip-compile` 产物，可重现性差。`numpy>=2.1.0` 与 `simple-lama-inpainting` / opencv 可能存在 ABI 风险。`edge-tts` / `redis` / `sqlalchemy` 已注释但 `=6.1.10` 表明实际在装 edge-tts——需求与实际脱节。建议拆分 `requirements/base.txt`、`requirements/dev.txt`、`requirements/musetalk.txt` 并产出锁定文件。

**.gitignore 缺失**：`models/`、`third_party/`、`test_outputs/`、`downloaded_images/`、`*.jpg` / `*.png` 调试截图、`*.html` 调试样本、`*_backup.py`、`quick_analysis.json` 等调试 JSON。已覆盖 `__pycache__`、`.venv`、`data/`、`logs/`、`.env`、`.pytest_cache`、`*.mp4`。

**测试组织**：根目录散落 50+ `test_*.py`，多为一次性脚本（无 assert、无 pytest 集成），仅 `tests/` 下 2 个文件（`test_title_units.py`、`test_animated_title_resolve.py`）是正规单测。**无 `pytest.ini` / `pyproject.toml` / `conftest.py` / `tox.ini`，无 CI**（`.github/` 仅含 `copilot-instructions.md`，无 `workflows/`）。

**文档治理**：`PROJECT_STATUS.md` 停留在 2026-02-05 且视频生成写 0%，已严重过时；`CRAWLER_STATUS.md`、`ARCHITECTURE_REFACTOR_PROGRESS.md`、`VIDEO_EMBEDDING_IMPLEMENTATION_REPORT.md`、`VentureBeat_Crawling_Summary.md` 均为阶段性快照报告，与 `INSTRUCTION.md`（较新、权威）和 `docs/` 重复甚至冲突。建议保留 `README.md` + `INSTRUCTION.md` + `docs/`，其余归档到 `docs/archive/` 或删除。

**改进建议**：
- **P0** 删除 `=6.1.10`、`pkg_resources.py`、`xtcocotools/`、调试 HTML/JSON/截图；修正 setup 脚本里的 `>=` 引号问题。
- **P0** 根目录 50+ `test_*.py` / `debug_*.py` / `quick_*.py` 批量清理或归档。
- **P0** `.gitignore` 补齐 `models/`、`third_party/`、`test_outputs/`、`downloaded_images/`、调试媒体/HTML/JSON。
- **P1** 依赖拆分 base/dev/musetalk，引入 `pip-compile` 锁定版本；显式声明 ffmpeg 系统依赖。
- **P1** 补 `pytest.ini` + `conftest.py`，把 `tests/` 正规化；新增 `.github/workflows/test.yml` 跑单测。
- **P1** 有价值工具脚本统一迁入 `scripts/` 并加 `scripts/README.md`。
- **P2** 文档归档——过时 STATUS/REPORT 合并进 `INSTRUCTION.md` 或 `docs/archive/`。
- **P2** `app.py` / `server.py` 空文件、`web_server_backup.py` 删除；`setup_*_env.bat` 改为幂等可重入，记录到 `docs/dev-setup.md`；引入 `pre-commit`（ruff + mypy + 大文件/敏感信息检查）。

**优点**：`INSTRUCTION.md` 写得清晰权威，明确「代码与本文为准」覆盖旧文档；`scripts/` 已有少量正经工具（`bootstrap_indextts_runtime.py`、`extract_index_assets.py`、`rewrite_index_html.py`、`split_index_js.py`）；`tests/` 目录虽小但有真正的单测；`requirements.txt` 注释清晰、`audioop-lts` 条件依赖处理到位；`.gitignore` 已覆盖核心运行时产物；`docs/` 有结构化分章文档；`.github/copilot-instructions.md` 体现 AI 协作规范意识。

---

## 3. 横切关注点（Cross-Cutting）

### 3.1 安全

| 风险 | 位置 | 严重度 |
|---|---|---|
| CORS 全通配 + credentials | `web_server.py` | 高 |
| `/replace-edited-image` 路径穿越 | `watermark_routes.py` | 高 |
| Wav2Lip `torch.load` 无 `weights_only` | `lip_sync/` | 高 |
| 权重下载无 SHA256 校验 | `download_*.py` | 中 |
| 上传仅校验扩展名无 magic bytes | `digital_human_routes.py` | 中 |
| `METAHUMAN_REFERENCE_DIR` 外引目录 | `digital_human_service.py` | 中 |
| 错误 detail 泄露内部绝对路径 | 多处 `HTTPException(detail=str(e))` | 低 |

### 3.2 资源管理

| 问题 | 位置 |
|---|---|
| 浏览器/驱动未 try/finally 关闭 | `crawler_service`、`src/crawlers/base` |
| `cv2.VideoCapture` 异常不释放 | `video_thumbnail_service` |
| 中间产物无 TTL | `data/generated/`、`data/uploaded/` |
| 任务态仅内存 | `DigitalHumanService.tasks` |
| 无 GPU 互斥 | lip_sync 全引擎 |

### 3.3 重复实现清单

| 重复对 | 处置 |
|---|---|
| `github_screenshot_service` ↔ `selenium_screenshot_service` | 合并为策略对象 |
| `services/video_service.py::create_video_frames` ↔ `utils/video_utils._render_frame_animated` | 合并标题/摘要绘制 |
| `github_voiceover_service` 字幕分段 ↔ 主管线字幕工具 | 抽 `utils/subtitle_*` |
| `CrawlerService.download_image` ↔ `RelatedImageService` ↔ `ImageManager` | 抽 `HttpDownloader` |
| 三份 VentureBeat 解析（`async_article_crawler` / `src/crawlers/venturebeat_crawler` / `universal_article_crawler`） | 收敛为一份 |
| nav/CSS 在 4 个 HTML 复制 | 抽 `partials/nav.html` + `tokens.css` |
| `video_routes.create-video` ↔ `create-user-video` ↔ `create-animated-video` | 抽 `services/animated_video_builder.py` |

### 3.4 死代码清单

- `app.py`、`server.py`、`web_server_backup.py`（入口）
- `src/crawlers/` 全模块（爬虫）
- `universal_article_crawler.py`
- `crawler_service.extract_content` 重复视频提取块（L250–279 与 L291–319）
- `gif_processor.py` MoviePy 1.x 导入路径
- `web_server_backup.py`、`=6.1.10`、`pkg_resources.py`、`xtcocotools/`

---

## 4. 推荐治理路线图

### 阶段一（1–2 天，安全与卫生）
1. 删除三个死入口 + `=6.1.10` + `pkg_resources.py` + `xtcocotools/` + 调试媒体/HTML/JSON。
2. `.gitignore` 补齐 `models/` / `third_party/` / `test_outputs/` / `downloaded_images/` / 调试媒体。
3. 根目录 50+ `test_*.py` / `debug_*.py` / `quick_*.py` 批量清理或迁入 `tests/legacy/`；`download_*.py` / `setup_*.bat` 迁入 `scripts/setup/`。
4. CORS 收敛 + `/replace-edited-image` 套 Pydantic + 路径白名单。
5. Wav2Lip `torch.load(..., weights_only=True)`；权重下载加 SHA256 校验文件。

### 阶段二（3–5 天，配置与依赖）
1. 引入 `services/paths.py` 集中路径管理；硬编码绝对路径全改 env var。
2. 依赖拆分 base/dev/musetalk + `pip-compile` 锁定；显式声明 ffmpeg 系统依赖。
3. 补 `pytest.ini` + `conftest.py` + `.github/workflows/test.yml`。
4. 抽 `HttpDownloader` + `RetryPolicy`；`CrawlerService` 改 `asyncio.to_thread` 或 `httpx`。
5. 文档归档：过时 STATUS/REPORT 合并进 `INSTRUCTION.md` 或 `docs/archive/`。

### 阶段三（5–10 天，重复消除与拆分）
1. 合并截图双引擎、视频标题/摘要绘制双套、字幕双套、HTTP 下载三套。
2. 拆分 `video_routes.py`（1314 行）与 `main.js`（2888 行）。
3. `DigitalHumanService` 任务态落 SQLite + GPU 信号量；进度改 SSE。
4. 中间产物 TTL + 后台清理任务。
5. 前端抽 `partials/nav.html` + `css/tokens.css` + `apiClient` + `pollTask`。

### 阶段四（持续，性能与体验）
1. `write_videofile(threads=..., preset='medium')`；分段帧并行渲染；删除逐像素 Python 双循环。
2. a11y 修复 + 响应式断点 + 资源压缩（字体 woff2 子集化、mp3 128 kbps、bg.png webp）。
3. GitHub API 速率限制感知 + 429 退避；Star History 本地栅格化。
4. `mode=ai` 全不可用时自动降级 fast 并告警。
5. 引入 `pre-commit`（ruff + mypy + 大文件/敏感信息检查）。

---

## 5. 各模块「值得保留的优点」汇总

- **API 层**：Pydantic v2 校验完善；`_resolve_background_image_path` 与 pip `_resolve_path` 有路径穿越防护；阻塞调用统一 `asyncio.to_thread`；`digital_human_service` 用 `asyncio.Lock` 保护任务映射；上传有大小/类型限制；loguru 日志带 rotation；每个领域均有 `/health`。
- **Services 层**：`asyncio.to_thread` 隔离同步重活模式正确；独立线程 + `asyncio.run` 解决嵌套事件循环；GitHub API 回退链鲁棒；README 图片优先级排序合理；Windows + Python 3.13 多级回退覆盖兼容性边缘情况。
- **视频管线**：`_safe_paste` 处理画面外裁剪；`title_units.py` 汉字当量截断是严谨的本地化长度控制；`scroll_up` 匀速模型物理直观；摘要高亮（长词优先、`re.escape`、描边）完整；PIP 快进策略巧妙；`asyncio.to_thread` 让出事件循环。
- **数字人/TTS**：引擎三档回退 + `availability_reason()` 诊断详尽；子进程隔离独立 conda env，避免 torch/mmcv/transformers 版本污染；`indextts_worker.py` v1/v2 config 兼容性处理细致；ASS 字幕烧录算法（中英文混排、按字号换算像素、词边界回缩）成熟可复用；进度反馈粒度体验良好。
- **GitHub 管线**：服务分层清晰；镜像 env 变量零侵入；`find_cached_project_id` 缓存探测；Star History 自动 PIL 裁白边；metadata.json 每项目一份可调试；README 图片优先级排序合理。
- **前端**：`digital_human.js` 结构最现代，可作重构模板；toast 抽象已成型；state 单独拆出方向正确；step-indicator 多步骤向导 UX 模式清晰；BGM/字体列表走后端 API 动态加载并有 fallback。
- **运维**：`INSTRUCTION.md` 清晰权威；`scripts/` 已有正经工具；`tests/` 有真正单测；`requirements.txt` 注释清晰、`audioop-lts` 条件依赖处理到位；`docs/` 结构化分章；`.github/copilot-instructions.md` 体现 AI 协作规范意识。

---

## 附录 A：关键文件清单

| 模块 | 文件 |
|---|---|
| 入口 | `web_server.py`（在用）、`app.py` / `server.py` / `web_server_backup.py`（死） |
| 路由 | `api/routes/{crawler,github,video,watermark,main,digital_human,pip}_routes.py` |
| Schemas | `api/schemas/request_models.py` |
| 视频核心 | `services/video_service.py`、`utils/video_utils.py`、`services/gif_processor.py`、`services/video_embedding_service.py` |
| 字幕/标题 | `utils/title_units.py`、`utils/subtitle_fonts.py`、`utils/summary_highlights.py`、`utils/github_mirror.py` |
| 爬虫 | `services/crawler_service.py`、`services/async_article_crawler.py`、`src/crawlers/`（死） |
| GitHub | `services/github_*.py`、`src/models/github_models.py` |
| 数字人 | `services/digital_human_service.py`、`services/lip_sync/`、`services/indextts_worker.py`、`services/github_voiceover_service.py` |
| 前端 | `static/{index,video_maker,github_video_maker,digital_human}.html`、`static/js/index/{state,main,modal,init}.js` |
| 资源 | `static/fonts/subtitle/ZiHunYanBoSon.ttf`（2.3 MB）、`static/imgs/bg.png`（3.5 MB）、`static/music/*.mp3`（~15 MB） |
| 配置 | `requirements.txt`、`.env.example`、`config/sources.yaml`、`src/utils/config.py` |
| 文档 | `README.md`、`INSTRUCTION.md`、`docs/01~07-*.md`、`PROJECT_STATUS.md`（过时） |

## 附录 B：审计方法

由 7 个并行子代理分别审计：API/Web 层、Services 业务层、视频生成管线、数字人/TTS、GitHub 视频管线、前端 UX、仓库卫生与运维。每个代理只读不写，返回结构化总结（关键问题、改进建议 P0/P1/P2、值得保留的优点）。本文为汇总产物。
