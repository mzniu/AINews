"""Uvicorn worker count helpers shared by web_server startup."""
from __future__ import annotations

import os
import sys


def effective_uvicorn_workers() -> int:
    """Effective worker count after platform caps (Windows → max 1)."""
    default_workers = "1" if sys.platform == "win32" else "4"
    workers = int(os.getenv("UVICORN_WORKERS", default_workers))
    if sys.platform == "win32" and workers > 1:
        workers = 1
    return workers
