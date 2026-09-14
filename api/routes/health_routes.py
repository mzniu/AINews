"""Health check endpoints for desktop shell and monitoring."""
from __future__ import annotations

from fastapi import APIRouter

from src.utils.paths import get_data_dir, is_packaged

router = APIRouter(prefix="/api", tags=["health"])

APP_VERSION = "1.0.2"


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "data_dir": str(get_data_dir()),
        "packaged": is_packaged(),
    }


@router.get("/desktop/auth-status")
def desktop_auth_status():
    from services.desktop_auth_status import get_desktop_auth_status

    return get_desktop_auth_status()
