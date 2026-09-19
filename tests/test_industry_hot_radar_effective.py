"""M0b: hot radar respects effective pack board enablement."""
from __future__ import annotations

import pytest

from services.industry.config_loader import build_effective_config, write_effective_cache
from services.industry.constants import DEFAULT_INDUSTRY_ID
from services.ingestion.hot_radar_settings import enabled_boards


def test_enabled_boards_follow_effective_pack(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="test",
    )
    boards = enabled_boards()
    board_ids = {b["id"] for b in boards}
    assert "sina_ai" in board_ids
    assert "kr36_ai" in board_ids
    assert len(board_ids) == 7
