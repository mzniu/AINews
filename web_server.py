"""
AINews Web Server - 模块化架构版本
"""
import sys
import os

# 修复Windows控制台GBK编码无法输出emoji/中文的问题
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from dotenv import load_dotenv

# 导入路由模块
from api.routes.main_routes import router as main_router
from api.routes.crawler_routes import router as crawler_router
from api.routes.video_routes import router as video_router
from api.routes.watermark_routes import router as watermark_router
from api.routes.gif_routes import router as gif_router
from api.routes.github_routes import router as github_router
from api.routes.video_text_routes import router as video_text_router  # 新增视频文字路由
from api.routes.manual_content_routes import router as manual_content_router  # 新增手动内容路由
from api.routes.image_search_routes import router as image_search_router
from api.routes.cover_image_routes import router as cover_image_router
from api.routes.related_image_routes import router as related_image_router
from api.routes.digital_human_routes import router as digital_human_router
from api.routes.pip_routes import router as pip_router

# 加载环境变量
load_dotenv()

# 配置日志
logger.add("logs/web_server_{time}.log", rotation="10 MB")

# 创建FastAPI应用
app = FastAPI(
    title="AINews API",
    version="2.0.0",
    description="AI资讯视频生成平台",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory="data"), name="data")

# 注册路由
print("正在注册路由...")
app.include_router(crawler_router)
app.include_router(video_router)
app.include_router(watermark_router)
app.include_router(gif_router)
app.include_router(github_router)
app.include_router(video_text_router)  # 注册视频文字路由
app.include_router(manual_content_router)  # 注册手动内容路由
app.include_router(image_search_router)
app.include_router(cover_image_router)
app.include_router(related_image_router)
app.include_router(digital_human_router)
app.include_router(pip_router)
# main_routes 放在最后，避免被其他路由覆盖，并添加 API 前缀
print(f"main_router: {main_router}")
app.include_router(main_router)
print("路由注册完成")

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8088"))
    # 多进程 worker：适合 CPU 密集；与 asyncio.to_thread 可同时使用（多页并发 + 单进程内不阻塞）
    workers = int(os.getenv("UVICORN_WORKERS", "1"))

    print("🚀 AINews API服务已启动")
    print(f"🌐 访问: http://localhost:{port}")
    print(f"📖 API文档: http://localhost:{port}/docs")
    print("\n⚙️  配置DeepSeek API Key:")
    print("   编辑 .env 文件，设置 DEEPSEEK_API_KEY=你的密钥")
    if workers > 1:
        print(f"\n🔧 UVICORN_WORKERS={workers}（多进程，需使用模块路径启动）\n")
    else:
        print()

    if workers > 1:
        uvicorn.run(
            "web_server:app",
            host="0.0.0.0",
            port=port,
            workers=workers,
            log_level="info",
        )
    else:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")