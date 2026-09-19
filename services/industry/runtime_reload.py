"""Reload ingestion/hot-radar runtime after active L2 changes."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.registry import sync_sources_to_db
from services.ingestion.worker import (
    get_ingestion_worker_mode,
    request_ingestion_schedule_reload,
)


def reload_industry_runtime(
    db: Session,
    worker: Any | None,
) -> dict[str, bool]:
    """Sync enabled sources from effective pack and refresh worker schedules."""
    sync_sources_to_db(db)
    embedded_refreshed = False
    separate_signaled = False
    if worker is not None:
        worker.refresh_schedules()
        embedded_refreshed = True
    elif get_ingestion_worker_mode() == "separate":
        request_ingestion_schedule_reload()
        separate_signaled = True
    runtime_reloaded = embedded_refreshed or separate_signaled
    return {
        "runtime_reloaded": runtime_reloaded,
        "embedded_schedules_refreshed": embedded_refreshed,
        "separate_worker_signaled": separate_signaled,
        "restart_required": False,
    }
