"""Tests for vision-model image batch scoring."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from services.ingestion.image_score_vl import (
    _build_prompt,
    _encode_image_data_url,
    _parse_vl_response,
    _resolve_max_tokens,
    _resolve_vl_timeouts,
    score_images_batch,
)


@pytest.fixture
def sample_image(tmp_path):
    path = tmp_path / "sample.jpg"
    Image.new("RGB", (400, 300), color=(10, 120, 200)).save(path)
    return path


def test_encode_image_data_url_returns_jpeg_data_url(sample_image):
    url = _encode_image_data_url(sample_image, max_edge_px=1280)
    assert url.startswith("data:image/jpeg;base64,")
    assert len(url) > 100


def test_build_prompt_includes_article_context():
    prompt = _build_prompt(
        article_title="DeepSeek 发布新模型",
        article_summary="重要快讯",
        keywords=["AI", "DeepSeek"],
        content_excerpt="正文节选",
        image_ids=["img1", "img2"],
    )
    assert "DeepSeek" in prompt
    assert "img1" in prompt
    assert "img2" in prompt
    assert "cover_fit" in prompt
    assert "figure_prominence" in prompt
    assert "8" in prompt and "12" in prompt
    assert "chapter_title" in prompt
    assert "JSON" in prompt


def test_parse_vl_response_extracts_image_scores():
    raw = json.dumps(
        {
            "images": [
                {
                    "source_id": "img1",
                    "dimensions": {
                        "topic_relevance": {"score": 8, "signals": ["test"]},
                        "info_value": {"score": 7, "signals": []},
                        "visual_quality": {"score": 9, "signals": []},
                        "flash_fit": {"score": 8, "signals": []},
                        "compliance": {"score": 9, "signals": []},
                    },
                    "penalties": [],
                    "caption": "截图",
                    "verdict": "可用",
                    "reject": False,
                }
            ]
        }
    )
    parsed = _parse_vl_response(raw, expected_ids=["img1"])
    assert len(parsed) == 1
    assert parsed[0]["source_id"] == "img1"
    assert parsed[0]["dimensions"]["topic_relevance"]["score"] == 8


def test_parse_vl_response_handles_code_fence_and_trailing_commas():
    raw = """```json
{
  "images": [
    {
      "source_id": "img1",
      "dimensions": {
        "topic_relevance": {"score": 8, "signals": []},
        "info_value": {"score": 7, "signals": []},
        "visual_quality": {"score": 9, "signals": []},
        "flash_fit": {"score": 8, "signals": []},
        "compliance": {"score": 9, "signals": []},
      },
      "penalties": [],
      "caption": "截图",
      "verdict": "可用",
      "reject": false,
    },
  ],
}
```"""
    parsed = _parse_vl_response(raw, expected_ids=["img1"])
    assert len(parsed) == 1
    assert parsed[0]["source_id"] == "img1"


def test_parse_vl_response_returns_empty_for_invalid_json():
    parsed = _parse_vl_response("{not valid json at all", expected_ids=["img1"])
    assert parsed == []


def test_resolve_max_tokens_scales_with_image_count():
    tokens = _resolve_max_tokens(
        {"max_tokens": 2048},
        image_count=2,
        vl_cfg={"max_tokens_per_image": 700, "min_max_tokens": 2048, "max_max_tokens": 8192},
    )
    assert tokens >= 2048
    assert tokens >= 700 * 2 + 256


def test_score_images_batch_calls_vision_client(sample_image, monkeypatch):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "images": [
                            {
                                "source_id": "img1",
                                "dimensions": {
                                    "topic_relevance": {"score": 8, "signals": []},
                                    "info_value": {"score": 8, "signals": []},
                                    "visual_quality": {"score": 8, "signals": []},
                                    "flash_fit": {"score": 8, "signals": []},
                                    "compliance": {"score": 8, "signals": []},
                                },
                                "penalties": [],
                                "caption": "test",
                                "verdict": "ok",
                                "reject": False,
                            }
                        ]
                    }
                )
            )
        )
    ]
    mock_client.chat.completions.create.return_value = mock_response

    profile = {
        "id": "test_vl",
        "model": "test-model",
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    monkeypatch.setattr(
        "services.ingestion.image_score_vl.get_vision_client",
        lambda: (mock_client, profile),
    )

    results = score_images_batch(
        article_title="测试",
        article_summary="摘要",
        keywords=["AI"],
        content_excerpt="正文",
        images=[("img1", sample_image)],
    )
    assert len(results) == 1
    assert results[0]["source_id"] == "img1"
    mock_client.chat.completions.create.assert_called_once()


def test_resolve_vl_timeouts_uses_batch_and_single_values():
    batch_timeout, single_timeout = _resolve_vl_timeouts(
        {"batch_timeout_sec": 120, "single_timeout_sec": 45, "request_timeout_sec": 30},
        image_count=4,
    )
    assert batch_timeout == 120
    assert single_timeout == 45

    one_batch, one_single = _resolve_vl_timeouts(
        {"batch_timeout_sec": 120, "single_timeout_sec": 45},
        image_count=1,
    )
    assert one_batch == 45
    assert one_single == 45


def test_score_images_batch_falls_back_to_single_on_batch_timeout(sample_image, monkeypatch):
    mock_client = MagicMock()
    def _create(**kwargs):
        content = kwargs.get("messages", [{}])[0].get("content", [])
        image_parts = [part for part in content if isinstance(part, dict) and part.get("type") == "image_url"]
        if len(image_parts) > 1:
            raise TimeoutError("Request timed out.")
        source_id = "img1"
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and "图片 ID:" in part.get("text", ""):
                source_id = part["text"].split("图片 ID:", 1)[1].strip()
                break
        return MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content=json.dumps(
                            {
                                "images": [
                                    {
                                        "source_id": source_id,
                                        "dimensions": {
                                            "topic_relevance": {"score": 8, "signals": []},
                                            "info_value": {"score": 8, "signals": []},
                                            "visual_quality": {"score": 8, "signals": []},
                                            "flash_fit": {"score": 8, "signals": []},
                                            "compliance": {"score": 8, "signals": []},
                                        },
                                        "penalties": [],
                                        "caption": "test",
                                        "verdict": "ok",
                                        "reject": False,
                                    }
                                ]
                            }
                        )
                    )
                )
            ]
        )

    mock_client.chat.completions.create.side_effect = _create

    profile = {"id": "test_vl", "model": "test-model", "max_tokens": 2048, "temperature": 0.3}
    monkeypatch.setattr(
        "services.ingestion.image_score_vl.get_vision_client",
        lambda: (mock_client, profile),
    )

    results = score_images_batch(
        article_title="测试",
        article_summary="摘要",
        keywords=["AI"],
        content_excerpt="正文",
        images=[("img1", sample_image), ("img2", sample_image)],
        config={"vl": {"max_retries": 0, "batch_timeout_sec": 30, "single_timeout_sec": 30}},
    )
    assert len(results) == 2
    assert {item["source_id"] for item in results} == {"img1", "img2"}
    assert mock_client.chat.completions.create.call_count >= 2


def test_score_images_batch_raises_without_client(monkeypatch, sample_image):
    monkeypatch.setattr(
        "services.ingestion.image_score_vl.get_vision_client",
        lambda: (None, None),
    )
    with pytest.raises(RuntimeError, match="视觉模型"):
        score_images_batch(
            article_title="t",
            article_summary=None,
            keywords=[],
            content_excerpt=None,
            images=[("img1", sample_image)],
        )
