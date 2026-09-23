"""Pattern card v2 validation."""
from __future__ import annotations

import yaml

from services.copy_agent.card_schema import validate_card
from tests.playbook_card_fixtures import minimal_card_yaml


def test_valid_minimal_card_passes():
    card = yaml.safe_load(minimal_card_yaml())
    assert validate_card(card, "开源模型三年对三天训练") == []


def test_rejects_verdict_function_sentence():
    card = yaml.safe_load(minimal_card_yaml())
    card["verdict"]["function"] = "网友：这也太快了"
    issues = validate_card(card, "三年对三天")
    assert any("verdict.function" in line for line in issues)


def test_rejects_long_evidence_excerpt():
    card = yaml.safe_load(minimal_card_yaml())
    card["evidence_excerpt"] = "x" * 81
    issues = validate_card(card, "x" * 81)
    assert any("evidence_excerpt" in line for line in issues)


def test_rejects_copied_pattern_name():
    material = "某巨头宣布开源新模型引发行业震动"
    card = yaml.safe_load(minimal_card_yaml(anchor="行业震动"))
    card["pattern"]["name"] = material
    issues = validate_card(card, material)
    assert any("pattern.name" in line for line in issues)
