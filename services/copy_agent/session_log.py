"""Human-readable curate session log for the pattern lab (not raw engineer dumps)."""
from __future__ import annotations

import json
from typing import Any


def last_turn_end_reason(log_text: str) -> str | None:
    reason = None
    for line in (log_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "turn/end":
            continue
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        end = data.get("reason") if isinstance(data.get("reason"), dict) else {}
        kind = end.get("kind")
        if kind:
            reason = str(kind)
    return reason


def summarize_session_log(log_text: str, *, max_entries: int = 200) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    for line in (log_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        entry = _entry_from_payload(payload)
        if entry:
            entries.append(entry)
    trimmed = entries[-max_entries:]
    text_lines = [f"[{item['kind']}] {item['text']}" for item in trimmed]
    return {"entries": trimmed, "text": "\n".join(text_lines)}


def _entry_from_payload(payload: dict[str, Any]) -> dict[str, str] | None:
    event_type = str(payload.get("type") or "")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    turn = data.get("turn")
    step = data.get("step")
    prefix = ""
    if turn:
        prefix = f"第 {turn} 轮"
        if step:
            prefix += f" 步骤 {step}"
        prefix += " · "

    if event_type == "turn/start":
        return {"kind": "轮次", "text": f"{prefix}开始"}
    if event_type == "turn/end":
        reason = ""
        end = data.get("reason") if isinstance(data.get("reason"), dict) else {}
        if end.get("kind"):
            reason = str(end["kind"])
        detail = _turn_end_label(reason)
        return {"kind": "轮次", "text": f"{prefix}结束" + (f"（{detail}）" if detail else "")}
    if event_type == "tool/call":
        name = str(data.get("name") or "tool")
        command = _command_from_arguments(str(data.get("arguments") or ""))
        short = command if len(command) <= 240 else command[:240] + "…"
        return {"kind": "工具", "text": f"{prefix}{name}: {short}"}
    if event_type == "tool/result":
        err = _tool_error(data)
        if err:
            return {"kind": "工具", "text": f"{prefix}返回错误：{err}"}
        return None
    if event_type == "assistant/message":
        text = _assistant_text(data)
        if text:
            short = text if len(text) <= 400 else text[:400] + "…"
            return {"kind": "模型", "text": f"{prefix}{short}"}
    return None


def _turn_end_label(kind: str) -> str:
    mapping = {
        "max-tokens": "达到输出长度上限",
        "completed": "正常完成",
        "tool-calls": "等待工具结果",
    }
    return mapping.get(kind, kind)


def _command_from_arguments(arguments: str) -> str:
    if not arguments:
        return ""
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    if isinstance(parsed, dict):
        return str(parsed.get("command") or arguments)
    return arguments


def _tool_error(data: dict[str, Any]) -> str | None:
    message = data.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("isError"):
            inner = block.get("content")
            if isinstance(inner, list) and inner:
                first = inner[0]
                if isinstance(first, dict) and first.get("text"):
                    return str(first["text"])[:200]
            return "执行失败"
    return None


def _assistant_text(data: dict[str, Any]) -> str | None:
    message = data.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool-call":
            return None
        if block.get("type") == "text" and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts) if parts else None
