"""日志配置模块"""
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv
import os

load_dotenv()

# 创建日志目录
log_dir = Path("data/logs")
log_dir.mkdir(parents=True, exist_ok=True)

# 移除默认处理器
logger.remove()

# 添加控制台输出
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=os.getenv("LOG_LEVEL", "INFO"),
    colorize=True
)

# 添加文件输出
log_file = os.getenv("LOG_FILE", "data/logs/ainews.log")
logger.add(
    log_file,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="1 day",
    retention="30 days",
    compression="zip"
)

__all__ = ["logger"]
