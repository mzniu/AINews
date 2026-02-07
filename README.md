# AINews - AI资讯视频生成器 🎬

一站式 AI 资讯处理工具：抓取网页内容 → DeepSeek AI 智能总结 → 自动生成竖屏短视频

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![MoviePy](https://img.shields.io/badge/MoviePy-2.x-red.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ 功能特性

- 🌐 **智能网页抓取** - 基于 Playwright，支持 JavaScript 渲染页面，自动提取正文和图片
- 🤖 **AI 内容总结** - 接入 DeepSeek API，自动生成 25 字标题、100 字摘要和 10 个热门标签
- 🎨 **关键帧生成** - 自动合成竖屏关键帧（1080×1920），包含背景模板、文章图片、标题和摘要
- 🎬 **视频合成** - MoviePy 2.x 一键合成 MP4，支持背景音乐和智能帧时长控制
- 🧹 **图片去水印** - 基于 LaMa 模型的 AI 图片修复，框选区域即可去除水印
- 📱 **Web 可视化界面** - 全流程浏览器操作，无需命令行

## 🖼️ 工作流程

```
输入URL → 抓取网页内容 → 编辑/选图 → AI总结 → 生成关键帧 → 合成视频 → 下载
```

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/AINews.git
cd AINews
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
# 安装 Playwright 浏览器
playwright install chromium
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key
```

### 5. 准备资源文件

- 背景模板：将 1080×1920 的背景图放到 `static/imgs/bg.png`
- 背景音乐（可选）：将 MP3 文件放到 `static/music/background.mp3`

如果没有背景图，可运行以下命令生成默认渐变背景：

```bash
python create_default_bg.py
```

### 6. 启动服务

```bash
python web_server.py
```

访问 http://localhost:8000 即可使用。API 文档：http://localhost:8000/docs

## 📖 使用说明

### 基本流程

1. **输入 URL** - 粘贴 AI 资讯文章链接，点击「抓取」
2. **编辑内容** - 修改标题、正文，勾选需要的图片
3. **AI 总结** - 点击「AI总结」，自动生成标题、摘要和标签
4. **生成关键帧** - 选择图片后点击「生成关键帧」，预览竖屏画面
5. **合成视频** - 点击「制作视频」，等待 MP4 生成后下载
6. **去水印**（可选）- 在图片查看器中框选水印区域，AI 自动修复

### 帧时长规则

| 关键帧数量 | 时长分配 |
|-----------|---------|
| 1 帧 | 6 秒 |
| 2 帧 | 每帧 3 秒 |
| 3+ 帧 | 首帧 2.5 秒，其余 3 秒 |

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 网页抓取 | Playwright (Chromium) + BeautifulSoup4 |
| AI 引擎 | DeepSeek API（OpenAI SDK 兼容） |
| 图像处理 | Pillow（合成、文字渲染、半透明遮罩） |
| 视频合成 | MoviePy 2.x（ImageClip → 拼接 → MP4） |
| 去水印 | simple-lama-inpainting（LaMa 模型） |
| 前端 | 原生 HTML/CSS/JavaScript |

## 📁 项目结构

```
AINews/
├── web_server.py          # 主服务（FastAPI 应用）
├── static/
│   ├── index.html         # 前端页面
│   ├── imgs/
│   │   └── bg.png         # 背景模板（1080×1920）
│   └── music/
│       └── background.mp3 # 背景音乐（需自行添加）
├── create_default_bg.py   # 生成默认背景图
├── src/
│   ├── crawlers/          # 爬虫模块
│   ├── models/            # 数据模型
│   └── utils/             # 工具函数
├── config/                # 配置文件
├── docs/                  # 设计文档
├── data/                  # 运行时数据（已gitignore）
│   ├── fetched/           # 抓取的内容和图片
│   └── videos/            # 生成的视频
├── requirements.txt
├── .env.example
└── .gitignore
```

## 📄 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Web 界面 |
| POST | `/api/fetch` | 抓取网页内容和图片 |
| POST | `/api/generate-summary` | AI 生成标题、摘要和标签 |
| POST | `/api/generate-image` | 生成视频关键帧 |
| POST | `/api/create-video` | 合成 MP4 视频 |
| POST | `/api/remove-watermark` | AI 去除图片水印 |
| POST | `/api/process-image` | 图片效果处理 |
| GET | `/api/health` | 健康检查 |

## 📚 文档

详细设计文档请查看 [docs/](docs/) 目录：

- [项目概述](docs/01-项目概述.md)
- [架构设计](docs/02-架构设计.md)
- [爬虫设计](docs/03-爬虫设计.md)
- [DeepSeek 集成](docs/04-DeepSeek集成.md)
- [视频生成](docs/05-视频生成.md)
- [技术栈](docs/06-技术栈.md)

## ⚠️ 注意事项

- **DeepSeek API Key** - 必须在 `.env` 中配置，建议控制日调用成本
- **Playwright 浏览器** - 首次使用需运行 `playwright install chromium`
- **背景音乐** - `static/music/background.mp3` 需自行提供（已 gitignore）
- **磁盘空间** - 生成的视频约 50-100MB/个，注意清理 `data/videos/`
- **LaMa 模型** - 首次去水印时会自动下载模型（约 200MB）

## License

MIT
