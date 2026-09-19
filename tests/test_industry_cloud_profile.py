"""M0c cloud active-industry stub."""
from __future__ import annotations

import pytest

from services.industry.cloud_profile import put_cloud_active_industry


def test_put_cloud_active_industry_local_when_no_base(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AINEWS_CLOUD_API_BASE", raising=False)
    result = put_cloud_active_industry("tech/ai")
    assert result["source"] == "local"
    assert result["synced"] is False
