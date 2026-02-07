# AI资讯视频生成器 - Copilot Instructions

## 项目概述
自动化AI资讯聚合系统：爬取多个AI资讯网站 → DeepSeek API智能总结 → 自动生成3-5分钟短视频

**核心工作流**: 爬虫 → 内容处理 → 视频生成

## 项目结构
```
src/
├── crawlers/        # 网站爬虫（Scrapy/BeautifulSoup）
├── processors/      # DeepSeek API集成和内容总结
├── generators/      # TTS + 字幕 + 视频合成（MoviePy）
├── models/          # SQLAlchemy数据模型
├── database/        # 数据库连接和迁移
└── utils/           # 日志、配置、工具函数
```

## 技术栈
- **Python 3.11+** - 主要开发语言
- **爬虫**: Scrapy + BeautifulSoup + Selenium
- **AI**: DeepSeek API（OpenAI SDK兼容）
- **视频**: MoviePy + Edge TTS + Pillow
- **存储**: PostgreSQL + Redis（去重缓存）

## 关键开发约定

### 1. 爬虫开发
- 继承 `BaseCrawler` 类实现新网站适配器
- 数据结构统一：title, url, source, content, publish_time 等
- 必须实现去重：URL哈希 + Redis Set
- 反爬策略：随机User-Agent、请求延迟1-3秒
- **⚠️ 禁止使用Mock数据：始终爬取真实网站内容**
- 网络问题时使用Selenium或RSS源作为备选方案

### 2. DeepSeek集成
- 使用 OpenAI SDK（DeepSeek兼容）
- Prompt模板位于 `processors/prompts.py`
- 输出验证：长度检查、格式检查、关键词检查
- 成本控制：缓存相同内容、批量处理

### 3. 视频生成
- 默认分辨率：1080x1920（竖屏，抖音/快手）
- TTS首选：Edge TTS（免费、音质好）
- 字幕样式：微软雅黑48号、白字黑边
- 模板位于 `generators/templates/`

### 4. 配置管理
- 环境变量使用 `.env` 文件（python-dotenv）
- 敏感信息（API Key）不提交到Git
- 爬虫源配置在 `config/sources.yaml`

## 常用命令

### 开发环境
```bash
# 安装依赖
pip install -r requirements.txt

# 运行爬虫 - 机器之心（需要代理）
python scripts/run_crawler.py --source jiqizhixin

# 运行爬虫 - 36氪AI频道（无需代理）
python test_36kr_complete.py

# 生成视频
python scripts/run_generator.py --date 2026-02-05

# 运行测试
pytest tests/ -v --cov
```

### 数据库操作
```bash
# 创建迁移
alembic revision -m "description"

# 应用迁移
alembic upgrade head
```

## 关键文件

- `src/crawlers/base.py` - 爬虫基类，所有爬虫继承此类
- `src/processors/deepseek.py` - DeepSeek API封装
- `src/generators/composer.py` - 视频合成核心逻辑
- `config/sources.yaml` - 爬虫网站配置
- `docs/` - 完整设计文档（架构、爬虫、API、视频生成等）

## 调试技巧

- **爬虫调试**: 使用 `scrapy shell` 交互式测试
- **视频预览**: MoviePy支持 `clip.preview()` 实时预览
- **日志**: 使用Loguru，日志级别在 `.env` 配置
- **性能分析**: 使用 `cProfile` 分析瓶颈

## 注意事项

⚠️ **反爬虫**: 爬取频率不超过每2小时一次，避免IP封禁  
⚠️ **API成本**: DeepSeek调用控制在每日1元预算内  
⚠️ **视频存储**: 单个视频约50-100MB，注意磁盘空间  
⚠️ **并发控制**: 视频生成使用多进程时注意内存占用

📚 **详细文档**: 查看 `docs/` 目录获取完整设计和实施计划

## 开发规范
- 遵循PEP8代码风格
- 每次请进行编译通过和单元测试