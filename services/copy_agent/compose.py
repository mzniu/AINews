"""Attach a playbook to the user message. The system role stays the constitution."""
from __future__ import annotations


def compose_copy_messages(
    *,
    methodology_user: str,
    playbook_body: str | None,
    system_role: str,
) -> list[dict]:
    user = methodology_user
    body = (playbook_body or "").strip()
    if body:
        user = f"{methodology_user}\n\n【打法】\n{body}"
    return [
        {"role": "system", "content": system_role},
        {"role": "user", "content": user},
    ]
