"""Turn dsh session logs into curate progress for the pattern lab UI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PHASE_PERCENT = {
    "preparing": 8,
    "running": 45,
    "auditing": 82,
    "validating": 90,
    "storing": 96,
    "done": 100,
    "failed": 100,
}


def read_live_session_text(session_root: Path) -> str:
    """Prefer the merged audit log; otherwise read the newest SDK session file."""
    target = session_root / "session.jsonl"
    if target.is_file() and target.stat().st_size:
        return target.read_text(encoding="utf-8", errors="replace")
    sessions = session_root / "sessions"
    if not sessions.is_dir():
        return ""
    candidates = [path for path in sessions.rglob("*.jsonl") if path.is_file()]
    if not candidates:
        return ""
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return newest.read_text(encoding="utf-8", errors="replace")


def parse_session_events(log_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in (log_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        event = _event_from_payload(payload)
        if event is None:
            continue
        key = f"{event.get('kind')}:{event.get('label')}:{event.get('turn')}:{event.get('step')}"
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def build_curate_progress(
    session_root: Path,
    workspace: Path,
    *,
    phase: str,
    phase_label: str,
    log_text: str | None = None,
) -> dict[str, Any]:
    text = log_text if log_text is not None else read_live_session_text(session_root)
    parsed = parse_session_events(text)
    turn = max((event.get("turn") or 0) for event in parsed) if parsed else 0
    step = max((event.get("step") or 0) for event in parsed) if parsed else 0
    drafts = workspace / "drafts"
    analysis_path = drafts / "analysis.md"
    card_path = drafts / "card.yaml"
    diff_path = drafts / "playbook.diff.yaml"
    artifacts = {
        "analysis_md": analysis_path.is_file() and analysis_path.stat().st_size > 0,
        "card_yaml": card_path.is_file() and card_path.stat().st_size > 0,
        "playbook_diff": diff_path.is_file() and diff_path.stat().st_size > 0,
    }
    base = _PHASE_PERCENT.get(phase, 10)
    bump = 0
    if artifacts.get("analysis_md"):
        bump += 6
    if artifacts["card_yaml"]:
        bump += 8
    if artifacts["playbook_diff"]:
        bump += 8
    if turn:
        bump += min(turn * 4, 16)
    if step:
        bump += min(step * 2, 12)
    percent = min(99 if phase not in {"done", "failed"} else 100, base + bump)
    return {
        "phase": phase,
        "phase_label": phase_label,
        "percent": percent,
        "turn": turn,
        "step": step,
        "events": parsed[-40:],
        "artifacts": artifacts,
    }


def _event_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(payload.get("type") or "")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    turn = int(data.get("turn") or 0) or None
    step = int(data.get("step") or 0) or None
    if event_type == "turn/start":
        label = f"开始第 {turn or 1} 轮拆卡"
        return {"kind": "turn", "label": label, "turn": turn, "step": step}
    if event_type == "turn/end":
        return {"kind": "turn", "label": "本轮拆卡结束", "turn": turn, "step": step}
    if event_type == "step/start" and step:
        return {"kind": "step", "label": f"第 {turn or 1} 轮 · 步骤 {step}", "turn": turn, "step": step}
    if event_type == "tool/call":
        label = _tool_label(str(data.get("name") or ""), str(data.get("arguments") or ""))
        return {"kind": "tool", "label": label, "turn": turn, "step": step}
    if event_type == "assistant/message" and not _message_has_tool_call(data):
        return {"kind": "model", "label": "模型正在整理拆卡结果", "turn": turn, "step": step}
    return None


def _message_has_tool_call(data: dict[str, Any]) -> bool:
    message = data.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(item, dict) and item.get("type") == "tool-call" for item in content)


def _tool_label(name: str, arguments: str) -> str:
    command = _extract_command(arguments).lower()
    if "material.txt" in command:
        return "正在阅读你贴的文案"
    if "schema.md" in command:
        return "正在阅读输出格式说明"
    if "analysis.md" in command:
        return "正在写入结构标注（analysis）"
    if "card.yaml" in command:
        return "正在写入模式卡"
    if "playbook.diff.yaml" in command or "playbook" in command:
        return "正在写入打法差异"
    if "get-childitem" in command or "get-location" in command or "dir" in command:
        return "正在查看草稿目录"
    if name == "pwsh" or name == "bash":
        return "正在执行草稿目录里的命令"
    return "正在调用工具"


def _extract_command(arguments: str) -> str:
    if not arguments:
        return ""
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    if isinstance(parsed, dict):
        return str(parsed.get("command") or "")
    return arguments
