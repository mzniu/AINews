from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.publishing.human_form import human_fill
from services.publishing.persona import (
    DEFAULT_PERSONA,
    ensure_persona_for_account,
    get_persona_pause_multiplier,
    load_persona,
    set_publish_persona_account,
)
from services.publishing.publish_warmup import load_publish_warmup_config, warmup_creator_session
from src.utils.config import Config


def test_load_publish_warmup_config_defaults():
    cfg = load_publish_warmup_config(
        {"defaults": {"publish_warmup": {"enabled": True, "idle_moves": [2, 5]}}}
    )
    assert cfg["enabled"] is True
    assert cfg["idle_moves"] == [2, 5]


def test_ensure_persona_for_account_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    persona = ensure_persona_for_account("acc1")
    assert persona["typing_delay_scale"] > 0
    path = tmp_path / "data" / "publish" / "persona" / "acc1.json"
    assert path.is_file()
    loaded = load_persona("acc1")
    assert loaded["pause_multiplier"] == persona["pause_multiplier"]


def test_persona_pause_multiplier_applies_in_pacing(monkeypatch):
    monkeypatch.setattr(
        "services.publishing.persona.load_persona",
        lambda _account_id: {**DEFAULT_PERSONA, "pause_multiplier": 2.0},
    )
    set_publish_persona_account("acc1")
    try:
        assert get_persona_pause_multiplier() == 2.0
    finally:
        set_publish_persona_account(None)


@patch("services.publishing.publish_warmup.human_idle_on_page")
@patch("services.publishing.publish_warmup.human_pause")
def test_warmup_creator_session_runs_idle(mock_pause, mock_idle):
    page = MagicMock()
    page.viewport_size = {"width": 1440, "height": 900}
    warmup_creator_session(page, platform_id="douyin")
    mock_idle.assert_called_once()
    mock_pause.assert_called_once()


@patch("services.publishing.human_form.human_type_text")
def test_human_fill_uses_type_text_for_input(mock_type):
    page = MagicMock()
    locator = MagicMock()
    locator.evaluate.return_value = "INPUT"
    human_fill(page, locator, "hello")
    mock_type.assert_called_once()
