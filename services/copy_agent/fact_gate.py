"""Fact gate and the fixed trap check. No model calls."""
from __future__ import annotations

import re

_TEN_X = re.compile(r"10\s*倍")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_MULTIPLE = re.compile(r"\d+(?:\.\d+)?\s*倍")


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


def _add(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)

