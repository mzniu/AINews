"""Tests for image deduplication by URL, path, and content description."""
from __future__ import annotations

from services.ingestion.image_dedupe import dedupe_image_entries, descriptions_similar


def test_descriptions_similar_for_near_duplicate_text():
    left = "OpenAI 发布会现场，Sam Altman 站在舞台中央介绍新模型"
    right = "发布会现场，Sam Altman 站在舞台中央介绍 OpenAI 新模型"
    assert descriptions_similar(left, right)


def test_dedupe_image_entries_by_content_description():
    images = [
        {
            "url": "https://cdn.example.com/a.jpg",
            "local_path": "/data/a.jpg",
            "content_description": "OpenAI 发布会现场，舞台中央展示新模型 Logo",
            "relevance_rank": 2,
            "relevance_score": 80,
        },
        {
            "url": "https://cdn.example.com/b.jpg",
            "local_path": "/data/b.jpg",
            "content_description": "发布会现场，舞台中央展示 OpenAI 新模型 Logo",
            "relevance_rank": 1,
            "relevance_score": 90,
        },
        {
            "url": "https://cdn.example.com/c.jpg",
            "local_path": "/data/c.jpg",
            "content_description": "产品界面截图，显示聊天输入框",
            "relevance_rank": 3,
            "relevance_score": 75,
        },
    ]
    deduped = dedupe_image_entries(images)
    assert len(deduped) == 2
    assert deduped[0]["relevance_rank"] == 1
