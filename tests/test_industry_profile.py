"""Local industry profile store (M0a)."""
from __future__ import annotations

import json

from services.industry.constants import DEFAULT_INDUSTRY_ID
from services.industry.profile import (
    activate_industry_l2,
    get_active_industry_id,
    load_industry_profile,
    needs_industry_onboarding,
    save_industry_profile,
)


def test_default_active_industry_without_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AINEWS_ACTIVE_INDUSTRY_ID", raising=False)
    monkeypatch.delenv("AINES_DEV_MODE", raising=False)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    assert get_active_industry_id() == DEFAULT_INDUSTRY_ID
    assert needs_industry_onboarding() is True


def test_env_overrides_profile_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", "finance/macro")
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    save_industry_profile("tech/digital")
    assert get_active_industry_id() == "finance/macro"


def test_save_and_load_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AINEWS_ACTIVE_INDUSTRY_ID", raising=False)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    save_industry_profile("sports/basketball")
    profile = load_industry_profile()
    assert profile["active_industry_id"] == "sports/basketball"
    assert get_active_industry_id() == "sports/basketball"
    cache_file = tmp_path / "cache" / "industry_profile.json"
    assert cache_file.is_file()
    on_disk = json.loads(cache_file.read_text(encoding="utf-8"))
    assert on_disk["active_industry_id"] == "sports/basketball"


def test_activate_industry_marks_onboarding_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AINES_DEV_MODE", raising=False)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    activate_industry_l2("tech/ai", sync_cloud=False)
    assert needs_industry_onboarding() is False
    profile = load_industry_profile()
    assert profile.get("onboarding_completed") is True
