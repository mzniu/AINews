"""Fact gate and the fixed trap check. No model calls."""
from __future__ import annotations

import re

_TEN_X = re.compile(r"10\s*倍")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_MULTIPLE = re.compile(r"\d+(?:\.\d+)?\s*倍")

FACT_GATE_POLICY_RULES = "rules-v1"
FACT_GATE_POLICY_DISABLED = "disabled"


def trap_check(draft_text: str) -> dict:
    text = draft_text or ""
    failures: list[str] = []
    if _TEN_X.search(text):
        failures.append("10倍")
    if "全面超越" in text:
        failures.append("全面超越")
    return {"passed": not failures, "failures": failures}


def fact_gate(draft_text: str, source_text: str) -> dict:
    draft = draft_text or ""
    source = source_text or ""
    source_compact = re.sub(r"\s+", "", source)
    violations: list[str] = []
    for number in _NUMBER.findall(draft):
        if number not in source:
            _add(violations, number)
    for multiple in _MULTIPLE.findall(draft):
        compact = re.sub(r"\s+", "", multiple)
        if compact not in source_compact:
            _add(violations, compact)
    if "全面超越" in draft and "全面超越" not in source:
        _add(violations, "全面超越")
    return {"passed": not violations, "violations": violations}


def fact_gate_disabled_result() -> dict:
    """Gate bypassed; draft remains selectable and pipeline keeps playbook attribution."""
    return {
        "passed": True,
        "skipped": True,
        "policy_version": FACT_GATE_POLICY_DISABLED,
        "violations": [],
    }


def evaluate_fact_gate(draft_text: str, source_text: str, *, enabled: bool) -> dict:
    if not enabled:
        return fact_gate_disabled_result()
    gate = fact_gate(draft_text, source_text)
    gate["policy_version"] = FACT_GATE_POLICY_RULES
    gate["skipped"] = False
    return gate


def fact_gate_summary(gate: dict | None) -> str:
    """Human-readable reason when fact_gate passed is false."""
    if not gate or gate.get("passed") or gate.get("skipped"):
        return ""
    violations = gate.get("violations")
    if not isinstance(violations, list) or not violations:
        return "口播里出现了素材正文中没有的数字、倍数或「全面超越」等表述"
    parts = [str(v) for v in violations[:6]]
    label = "、".join(parts)
    if len(violations) > 6:
        label += f" 等 {len(violations)} 项"
    return f"素材中找不到对应出处：{label}"


def _add(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)

