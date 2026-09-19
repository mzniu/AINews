"""Sync active L2 to cloud Control Plane (stub when offline)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from services.industry.constants import is_valid_industry_id


def put_cloud_active_industry(
    active_industry_id: str,
    *,
    access_token: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    if not is_valid_industry_id(active_industry_id):
        raise ValueError(f"Invalid industry_id: {active_industry_id}")
    base = os.getenv("AINEWS_CLOUD_API_BASE", "").strip().rstrip("/")
    token = (access_token or os.getenv("AINEWS_CLOUD_ACCESS_TOKEN") or "").strip()
    if not base:
        return {
            "source": "local",
            "active_industry_id": active_industry_id,
            "synced": False,
        }
    url = f"{base}/me/active-industry"
    body = json.dumps({"active_industry_id": active_industry_id}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict):
            payload["source"] = "cloud"
            payload["synced"] = True
            return payload
    except (urllib.error.URLError, ValueError, TypeError, json.JSONDecodeError, OSError):
        pass
    return {
        "source": "cloud",
        "active_industry_id": active_industry_id,
        "synced": False,
        "error": "cloud_unreachable",
    }
