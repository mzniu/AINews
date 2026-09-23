"""Body vs pattern card consistency checks."""
from __future__ import annotations

import yaml

from services.copy_agent.card_schema import validate_body_blocking, validate_body_warnings
from tests.playbook_card_fixtures import MINIMAL_PLAYBOOK_BODY, minimal_card_yaml


def test_blocking_rejects_short_body():
    card = yaml.safe_load(minimal_card_yaml())
    issues = validate_body_blocking(card, "太短")
    assert issues


def test_blocking_accepts_aligned_body():
    card = yaml.safe_load(minimal_card_yaml())
    assert validate_body_blocking(card, MINIMAL_PLAYBOOK_BODY) == []


def test_warnings_when_hook_cues_missing():
    card = yaml.safe_load(minimal_card_yaml())
    body = "x" * 40
    warnings = validate_body_warnings(card, body)
    assert any("钩子" in line for line in warnings)
