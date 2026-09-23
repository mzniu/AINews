"""Reload ingestion/hot-radar runtime after active L2 changes."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.ingestion.registry import sync_sources_to_db
from services.ingestion.worker import (
    get_ingestion_worker_mode,
    request_ingestion_schedule_reload,
)

logger = logging.getLogger(__name__)


def reload_industry_runtime(
    db: Session,
    worker: Any | None,
) -> dict[str, Any]:
    """Sync enabled sources from effective pack and refresh worker schedules."""
    embedded_refreshed = False
    separate_signaled = False
    reload_error: str | None = None

    try:
        sync_sources_to_db(db)
        db.commit()
    except SQLAlchemyError as exc:
        logger.warning("Industry runtime sync_sources_to_db failed: %s", exc)
        db.rollback()
        return {
            "runtime_reloaded": False,
            "embedded_schedules_refreshed": False,
            "separate_worker_signaled": False,
            "restart_required": False,
            "reload_error": str(exc),
        }

    if worker is not None:
        try:
            worker.refresh_schedules()
            embedded_refreshed = True
        except Exception as exc:
            logger.warning("Embedded ingestion worker schedule refresh failed: %s", exc)
            reload_error = str(exc)
    elif get_ingestion_worker_mode() == "separate":
        request_ingestion_schedule_reload()
        separate_signaled = True

    runtime_reloaded = embedded_refreshed or separate_signaled
    result: dict[str, Any] = {
        "runtime_reloaded": runtime_reloaded,
        "embedded_schedules_refreshed": embedded_refreshed,
        "separate_worker_signaled": separate_signaled,
        "restart_required": False,
    }
    if reload_error:
        result["reload_error"] = reload_error
    return result
