"""API路由模块"""
from api.routes.main_routes import router as main_router
from api.routes.crawler_routes import router as crawler_router
from api.routes.video_routes import router as video_router
from api.routes.watermark_routes import router as watermark_router
from api.routes.gif_routes import router as gif_router
from api.routes.github_routes import router as github_router

__all__ = [
    'main_router', 'crawler_router', 'video_router',
    'watermark_router', 'gif_router', 'github_router'
]