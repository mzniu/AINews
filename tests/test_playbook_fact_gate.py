"""Fact gate: numbers and comparatives must appear in the source text."""
from __future__ import annotations

from services.copy_agent.fact_gate import (
    evaluate_fact_gate,
    fact_gate,
    fact_gate_summary,
    trap_check,
)


def test_evaluate_fact_gate_skipped_when_disabled():
    gate = evaluate_fact_gate("快 10 倍", "无数字素材", enabled=False)
    assert gate["passed"] is True
    assert gate.get("skipped") is True


def test_trap_rejects_ten_x_and_universal_win():
    assert trap_check("快 10 倍，多项评测全面超越")["passed"] is False


def test_trap_allows_eight_x():
    assert trap_check("大约快 8 倍，可本地部署")["passed"] is True


def test_fact_gate_rejects_number_missing_from_source():
    result = fact_gate("耗时 3 年，3 天被追上", "社区用了很短时间做出对标实现")
    assert result["passed"] is False
    assert result["violations"]


def test_fact_gate_rejects_multiple_missing_from_source():
    result = fact_gate("快 8 倍", "社区对标实现")
    assert result["passed"] is False


def test_fact_gate_rejects_universal_win_missing_from_source():
    result = fact_gate("全面超越", "速度更快")
    assert result["passed"] is False


def test_fact_gate_summary_lists_violations():
    gate = fact_gate("快 10 倍", "社区对标")
    assert gate["passed"] is False
    summary = fact_gate_summary(gate)
    assert "素材中找不到" in summary
    assert "10" in summary or "10倍" in summary


def test_fact_gate_allows_numbers_copied_from_source():
    result = fact_gate("大约快 8 倍", "资料写明大约快 8 倍，可本地部署")
    assert result["passed"] is True
    assert result["violations"] == []
