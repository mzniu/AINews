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
app.include_router(main_router)
app.include_router(crawler_router)
app.include_router(video_router)
app.include_router(watermark_router)

if __name__ == "__main__":
    import uvicorn
    print("🚀 AINews API服务已启动")
    print("🌐 访问: http://localhost:8080")
    print("📖 API文档: http://localhost:8080/docs")
    print("\n⚙️  配置DeepSeek API Key:")
    print("   编辑 .env 文件，设置 DEEPSEEK_API_KEY=你的密钥\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")