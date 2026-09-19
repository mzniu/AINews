"""M0b: effective pack injects content methodology into shared prompt builder."""
from __future__ import annotations

import pytest

from services.industry.config_loader import build_effective_config, write_effective_cache
from services.industry.constants import DEFAULT_INDUSTRY_ID
from utils.content_methodology import build_methodology_prompt_section


def test_build_methodology_includes_pack_audience_and_praise_tags(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="test",
    )
    prompt = build_methodology_prompt_section(
        vmin=120,
        vmax=400,
        json_template='{"summary": ""}',
    )
    assert "AI 技术从业者与科技爱好者" in prompt
    assert "懂行" in prompt
    assert "【当前垂类行业包】" in prompt
