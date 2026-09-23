"""Reject headline-style forbidden_transfers and news-like playbook bodies."""
from __future__ import annotations

import yaml

from services.copy_agent.card_schema import validate_body_blocking, validate_card
from tests.playbook_card_fixtures import minimal_card_yaml


def test_rejects_headline_forbidden_transfers():
    material = (
        "三年心血Jev模型爆火败给3天开源Laya，闭源正在被开源快速撕碎，"
        "Laya推理速度快10倍，多项评测全面超越"
    )
    card = yaml.safe_load(minimal_card_yaml())
    card["transfer_rules"] = {
        "forbidden_transfers": [
            "三年心血Jev模型爆火败给3天开源Laya",
            "Laya推理速度快10倍",
        ]
    }
    issues = validate_card(card, material)
    assert any("forbidden_transfers" in line for line in issues)


def test_rejects_news_summary_body():
    material = "OpenAI 前核心研究员耗时近三年秘密打造决策模型 Jev。"
    card = yaml.safe_load(minimal_card_yaml())
    body = (
        "OpenAI 前核心研究员耗时近三年秘密打造决策模型 Jev，其公司获得 4000 万美元种子融资。\n"
        "社区开发者用三天时间开源 Laya，该模型支持 51 种语言。\n"
        "有评论认为，这一事件引发对闭源 AI 初创公司壁垒的讨论。"
    )
    issues = validate_body_blocking(card, body, material=material)
    assert issues
