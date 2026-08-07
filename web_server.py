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

from dotenv import load_dotenv

# 加载环境变量（须在日志配置前，以便读取 LOG_LEVEL / UVICORN_WORKERS）
load_dotenv()

# 统一日志配置（须在路由导入前，避免多 handler / 多进程抢同一日志文件）
from src.utils.logger import configure_logging, logger

configure_logging()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

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
from api.routes.compliance_routes import router as compliance_router
from api.routes.ingestion_routes import router as ingestion_router
from api.routes.publishing_routes import router as publishing_router
from api.routes.model_config_routes import router as model_config_router
from src.utils.uvicorn_workers import effective_uvicorn_workers

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
app.include_router(compliance_router)
app.include_router(ingestion_router)
app.include_router(publishing_router)
app.include_router(model_config_router)
# main_routes 放在最后，避免被其他路由覆盖，并添加 API 前缀
print(f"main_router: {main_router}")
app.include_router(main_router)
print("路由注册完成")


@app.on_event("startup")
def on_startup():
    from src.db.engine import init_db
    from services.ingestion.registry import sync_sources_to_db
    from src.db.engine import get_session_factory
    from services.publishing.worker import PublishWorker, get_publish_worker_mode

    init_db()
    with get_session_factory()() as session:
        sync_sources_to_db(session)
        session.commit()
    logger.info("Ingestion DB initialized")

    if get_publish_worker_mode() == "embedded":
        if effective_uvicorn_workers() > 1:
            logger.warning(
                "PUBLISH_WORKER_MODE=embedded 但 UVICORN_WORKERS>1，"
                "请改用 PUBLISH_WORKER_MODE=separate 并单独运行 publish worker"
            )
        else:
            try:
                worker = PublishWorker(embedded=True)
                worker.start_embedded()
                app.state.publish_worker = worker
                logger.info("Embedded publish worker active (PUBLISH_WORKER_MODE=embedded)")
            except Exception:
                logger.exception("内嵌 publish worker 启动失败")
    else:
        logger.info("Publish worker 未内嵌，请运行 scripts/run_publish_worker.bat")

    from services.ingestion.worker import IngestionWorker, get_ingestion_worker_mode

    if get_ingestion_worker_mode() == "embedded":
        if effective_uvicorn_workers() > 1:
            logger.warning(
                "INGESTION_WORKER_MODE=embedded 但 UVICORN_WORKERS>1，"
                "请改用 INGESTION_WORKER_MODE=separate 并单独运行 ingestion worker"
            )
        else:
            try:
                ingestion_worker = IngestionWorker(embedded=True)
                ingestion_worker.start_embedded()
                app.state.ingestion_worker = ingestion_worker
                logger.info("Embedded ingestion worker active (INGESTION_WORKER_MODE=embedded)")
            except Exception:
                logger.exception("内嵌 ingestion worker 启动失败")
    else:
        logger.info("Ingestion worker 未内嵌，请运行 python -m services.ingestion.worker")


@app.on_event("shutdown")
def on_shutdown():
    worker = getattr(app.state, "publish_worker", None)
    if worker is not None:
        worker.shutdown()
    ingestion_worker = getattr(app.state, "ingestion_worker", None)
    if ingestion_worker is not None:
        ingestion_worker.shutdown()


if __name__ == "__main__":
    import sys
    import uvicorn

    port = int(os.getenv("PORT", "8088"))
    # 多进程 worker：与 asyncio.to_thread 配合（多进程隔离 + 单进程内不阻塞 event loop）
    # 注意：>1 时数字人模块的内存态任务（task_id → 进度）无法跨进程共享，
    # 如依赖 /api/digital-human/progress 轮询，请保持 workers=1 或改用外部任务存储
    # Windows 上 uvicorn 多 worker 会因 socket 无法跨进程共享而报 WinError 10022
    workers = effective_uvicorn_workers()
    if sys.platform == "win32" and int(os.getenv("UVICORN_WORKERS", "1")) > 1:
        print(f"⚠️  Windows 不支持 uvicorn 多 worker（UVICORN_WORKERS={os.getenv('UVICORN_WORKERS')}），已降为 1")

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