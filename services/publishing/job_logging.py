"""Publish job scoped logging with timestamps."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import TYPE_CHECKING, Iterator

from loguru import logger

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

from src.db.models.publishing import PublishLog

_job_id_var: ContextVar[str | None] = ContextVar("publish_job_id", default=None)
_session_factory_var: ContextVar[sessionmaker | None] = ContextVar(
    "publish_session_factory",
    default=None,
)
_sink_installed = False

_PUBLISH_LOG_PREFIXES = ("services.publishing.",)


def format_log_timestamp(when: datetime | None = None) -> str:
    moment = when or datetime.now()
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def format_log_message(message: str, *, when: datetime | None = None) -> str:
    text = (message or "").strip()
    prefix = format_log_timestamp(when)
    if text.startswith(prefix):
        return text
    return f"{prefix} | {text}"


def record_job_log(
    session_factory: sessionmaker,
    job_id: str,
    message: str,
    *,
    level: str = "info",
    screenshot_path: str | None = None,
    when: datetime | None = None,
) -> None:
    with session_factory() as session:
        session.add(
            PublishLog(
                job_id=job_id,
                level=level,
                message=format_log_message(message, when=when),
                screenshot_path=screenshot_path,
            )
        )
        session.commit()


def _should_capture_publish_log(record_name: str) -> bool:
    return any(record_name.startswith(prefix) for prefix in _PUBLISH_LOG_PREFIXES)


def _job_log_sink(message) -> None:
    job_id = _job_id_var.get()
    session_factory = _session_factory_var.get()
    if not job_id or session_factory is None:
        return

    record = message.record
    if not _should_capture_publish_log(record["name"]):
        return

    level = record["level"].name.lower()
    if level == "success":
        level = "info"
    if level not in {"info", "warning", "error", "debug"}:
        level = "info"

    try:
        record_job_log(
            session_factory,
            job_id,
            record["message"],
            level=level,
            when=record["time"],
        )
    except Exception as exc:
        logger.debug("Publish job log sink skipped: {}", exc)


def install_publish_job_log_sink() -> None:
    global _sink_installed
    if _sink_installed:
        return
    logger.add(
        _job_log_sink,
        format="{message}",
        level="DEBUG",
        enqueue=True,
        catch=True,
    )
    _sink_installed = True


@contextmanager
def publish_job_scope(session_factory: sessionmaker, job_id: str) -> Iterator[None]:
    install_publish_job_log_sink()
    job_token = _job_id_var.set(job_id)
    factory_token = _session_factory_var.set(session_factory)
    try:
        yield
    finally:
        _session_factory_var.reset(factory_token)
        _job_id_var.reset(job_token)
