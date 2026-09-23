"""Playbook text is appended to the user message, never the system role."""
from __future__ import annotations

from services.copy_agent.compose import compose_copy_messages


def test_compose_omits_playbook_when_empty():
    msgs = compose_copy_messages(
        methodology_user="USER", playbook_body=None, system_role="SYS"
    )
    assert msgs[0]["content"] == "SYS"
    assert msgs[1]["content"] == "USER"


def test_compose_appends_playbook_to_user_only():
    msgs = compose_copy_messages(
        methodology_user="USER", playbook_body="对照放前三秒", system_role="SYS"
    )
    assert msgs[0]["content"] == "SYS"
    assert msgs[1]["content"].startswith("USER")
    assert msgs[1]["content"].endswith("\n\n【打法】\n对照放前三秒")


def test_generate_video_content_leaves_constitution_message_unchanged(monkeypatch):
    from types import SimpleNamespace

    from services.content_generation_service import generate_video_content

    captured = {}

    def fake_invoke(**kwargs):
        captured["messages"] = kwargs["messages"]
        return {"main_line1": "标题"}, SimpleNamespace(tokens_used=1, to_dict=lambda: {})

    monkeypatch.setattr(
        "services.content_generation_service.invoke_json_llm_with_compliance",
        fake_invoke,
    )
    monkeypatch.setattr(
        "services.content_generation_service._build_openai_client",
        lambda: (None, "deepseek-chat", "", {}),
    )
    generate_video_content(title="原标题", content="正文")
    plain = captured["messages"][1]["content"]
    system = captured["messages"][0]["content"]
    assert "【打法】" not in plain
    generate_video_content(title="原标题", content="正文", playbook_body="对照放前三秒")
    assert captured["messages"][0]["content"] == system
    assert captured["messages"][1]["content"] == plain + "\n\n【打法】\n对照放前三秒"
