"""日志配置模块（Loguru）

Windows + uvicorn 多 worker 时，多个进程不能共享同一可轮转日志文件（rename 会 WinError 32）。
默认按进程 PID 分文件：data/logs/ainews.<pid>.log
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger as _logger

_configured = False


def _resolve_log_path(base_log: str) -> str:
    """多进程 / Windows 下为每个进程使用独立日志路径，避免轮转抢锁。"""
    if "{pid}" in base_log:
        return base_log.format(pid=os.getpid())

    base_path = Path(base_log)
    workers = os.getenv("UVICORN_WORKERS", "1")
    multi_worker = workers not in ("", "1", "0")
    if multi_worker or sys.platform == "win32":
        return str(base_path.with_name(f"{base_path.stem}.{os.getpid()}{base_path.suffix}"))
    return base_log


def configure_logging():
    """配置 Loguru（幂等，每个进程只执行一次）。"""
    global _configured
    if _configured:
        return _logger

    load_dotenv()
    _configured = True

    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    _logger.remove()

    log_level = os.getenv("LOG_LEVEL", "INFO")
    console_fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    file_fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"

    _logger.add(
        sys.stdout,
        format=console_fmt,
        level=log_level,
        colorize=True,
        enqueue=True,
        catch=True,
    )

    base_log = os.getenv("LOG_FILE", "data/logs/ainews.log")
    log_path = _resolve_log_path(base_log)
    _logger.add(
        log_path,
        format=file_fmt,
        level=os.getenv("LOG_FILE_LEVEL", "DEBUG"),
        rotation=os.getenv("LOG_ROTATION", "10 MB"),
        retention=os.getenv("LOG_RETENTION", "30 days"),
        compression="zip",
        enqueue=True,
        catch=True,
    )

    return _logger


logger = configure_logging()

__all__ = ["logger", "configure_logging"]
