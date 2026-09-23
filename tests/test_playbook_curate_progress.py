"""Curate job progress: parse harness session into product-facing steps."""
from __future__ import annotations

import json
from pathlib import Path

from services.copy_agent.progress import build_curate_progress, parse_session_events


def test_parse_session_events_maps_tool_calls_to_chinese_labels():
    lines = [
        json.dumps({"type": "turn/start", "data": {"turn": 1}}),
        json.dumps(
            {
                "type": "tool/call",
                "data": {
                    "turn": 1,
                    "step": 1,
                    "name": "pwsh",
                    "arguments": '{"command": "Get-Content -Raw material.txt"}',
                },
            }
        ),
        json.dumps(
            {
                "type": "tool/call",
                "data": {
                    "turn": 1,
                    "step": 2,
                    "name": "pwsh",
                    "arguments": '{"command": "Set-Content drafts/card.yaml x"}',
                },
            }
        ),
    ]
    events = parse_session_events("\n".join(lines) + "\n")
    labels = [e["label"] for e in events]
    assert "开始第 1 轮拆卡" in labels
    assert "正在阅读你贴的文案" in labels
    assert "正在写入模式卡" in labels


def test_build_curate_progress_includes_artifacts(tmp_path):
    workspace = tmp_path / "ws"
    drafts = workspace / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "card.yaml").write_text("verdict:\n  kind: opinion\n", encoding="utf-8")
    session_root = tmp_path / "sess"
    session_root.mkdir()
    progress = build_curate_progress(
        session_root,
        workspace,
        phase="running",
        phase_label="智能体正在拆卡…",
        log_text="",
    )
    assert progress["phase"] == "running"
    assert progress["artifacts"]["card_yaml"] is True
    assert progress["artifacts"]["playbook_diff"] is False
    assert progress["percent"] >= 10
