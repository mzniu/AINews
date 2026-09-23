"""Session log summaries for the pattern lab."""
from __future__ import annotations

import json

from services.copy_agent.session_log import last_turn_end_reason, summarize_session_log


def test_last_turn_end_reason_reads_max_tokens():
    line = json.dumps({"type": "turn/end", "data": {"turn": 1, "reason": {"kind": "max-tokens"}}})
    assert last_turn_end_reason(line + "\n") == "max-tokens"


def test_summarize_session_includes_tool_and_turn_end():
    lines = [
        json.dumps({"type": "tool/call", "data": {"turn": 1, "step": 1, "name": "pwsh", "arguments": '{"command":"Get-Content material.txt"}'}}),
        json.dumps({"type": "turn/end", "data": {"turn": 1, "reason": {"kind": "max-tokens"}}}),
    ]
    summary = summarize_session_log("\n".join(lines) + "\n")
    assert "material.txt" in summary["text"]
    assert "达到输出长度上限" in summary["text"]
