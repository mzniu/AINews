"""Tests for shared video content generation service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.content_generation_service import generate_video_content


@patch("services.content_generation_service.invoke_json_llm_with_compliance")
@patch("services.content_generation_service._build_openai_client")
def test_generate_video_content_parses_llm_response(mock_client, mock_invoke):
    mock_client.return_value = (MagicMock(), "deepseek-chat", "https://api.deepseek.com")
    compliance = MagicMock()
    compliance.tokens_used = 100
    compliance.to_dict.return_value = {"passed": True}
    mock_invoke.return_value = (
        {
            "main_line1": "突发！DeepSeek 新模型",
            "main_line2": "网友：太强了",
            "sub_title": "小牛说副标题",
            "sub_title2": "",
            "summary": "小牛说：DeepSeek 发布新模型。",
            "voiceover_script": "小牛说：DeepSeek 发布新模型。",
            "tags": "#AI #DeepSeek",
            "target_audience": "AI从业者",
            "praise_tags": ["懂行"],
            "traffic_hook": "观众想看结果",
            "highlight_keywords": ["DeepSeek"],
        },
        compliance,
    )

    result = generate_video_content(
        title="原标题",
        content="DeepSeek 发布新模型正文。",
        voiceover_min_chars=40,
        voiceover_max_chars=90,
    )

    assert result["success"] is True
    assert result["main_line1"].startswith("突发")
    assert result["summary"].startswith("小牛说")
    assert "DeepSeek" in result["title"]
