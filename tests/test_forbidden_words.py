"""违禁词配置与合规扫描测试。"""
from pathlib import Path

import pytest

from utils.content_compliance import (
    build_retry_user_message,
    extract_fields_from_llm_result,
    validate_llm_result,
)
from utils.forbidden_words import (
    ForbiddenWordsRegistry,
    get_registry,
    reload_registry,
    scan_content_fields,
)


def test_registry_loads_default_categories():
    registry = reload_registry()
    ids = {category.id for category in registry.categories}
    assert "absolute_superlative" in ids
    assert "false_promise" in ids
    assert "platform_abuse" in ids


def test_scan_detects_substring_match():
    registry = reload_registry()
    violations = registry.scan_text("这是全网第一的方案", field="main_line1")
    assert any(item.matched == "全网第一" for item in violations)
    assert violations[0].severity == "error"


def test_scan_tags_strips_hash_prefix():
    registry = reload_registry()
    violations = registry.scan_text("#集赞 #AI资讯", field="tags")
    assert any(item.matched == "集赞" for item in violations)


def test_scan_clean_text_has_no_violations():
    registry = reload_registry()
    violations = registry.scan_text("突发！AI修Bug率飙八倍", field="main_line1")
    assert violations == []


def test_merge_local_config_appends_words(tmp_path, monkeypatch):
    base_path = tmp_path / "forbidden_words.yaml"
    local_path = tmp_path / "forbidden_words.local.yaml"
    base_path.write_text(
        """
version: 1
settings:
  hot_reload: false
categories:
  - id: absolute_superlative
    name: 绝对化
    enabled: true
    severity: error
    match: substring
    words: [最]
""".strip(),
        encoding="utf-8",
    )
    local_path.write_text(
        """
version: 1
categories:
  - id: custom_local
    name: 本地
    enabled: true
    severity: error
    match: substring
    words: [本地禁词]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("utils.forbidden_words.DEFAULT_CONFIG_PATH", base_path)
    monkeypatch.setattr("utils.forbidden_words.LOCAL_CONFIG_PATH", local_path)
    registry = ForbiddenWordsRegistry.load()
    words = {word for category in registry.categories for word in category.words}
    assert "最" in words
    assert "本地禁词" in words


def test_validate_llm_result_reports_field_level_violations():
    result = {
        "main_line1": "重磅！全网第一AI工具",
        "main_line2": "",
        "sub_title": "具体数字更有说服力",
        "sub_title2": "",
        "summary": "小牛说：这是一条合规摘要。",
        "voiceover_script": "小牛说：口播稿内容。",
        "tags": "#人工智能 #AI应用",
        "highlight_keywords": ["合规摘要"],
        "praise_tags": ["懂行"],
        "target_audience": "AI从业者",
    }
    compliance = validate_llm_result(result, registry=reload_registry())
    assert compliance.ok is False
    assert any(item.field == "main_line1" for item in compliance.violations)


def test_extract_fields_from_llm_result_normalizes_tags_list():
    fields = extract_fields_from_llm_result(
        {
            "main_line1": "来了！开源项目更新",
            "tags": ["#人工智能", "#小牛说"],
            "praise_tags": "认知高, 懂行",
            "highlight_keywords": "开源, 更新",
        }
    )
    assert fields["tags"] == "#人工智能 #小牛说"
    assert fields["praise_tags"] == ["认知高", "懂行"]
    assert fields["highlight_keywords"] == ["开源", "更新"]


def test_build_retry_user_message_contains_hits():
    registry = reload_registry()
    violations = registry.scan_text("100%有效承诺", field="summary")
    message = build_retry_user_message(violations)
    assert "100%有效" in message
    assert "summary" in message


def test_prompt_section_includes_migrated_words():
    registry = reload_registry()
    prompt = registry.build_prompt_section()
    assert "【禁限词与合规约束" in prompt
    assert "100%有效" in prompt
    assert "全网第一" in prompt
    assert "领导人姓名" in prompt
    assert "改写原则" in prompt


def test_scan_content_fields_covers_all_declared_fields():
    registry = reload_registry()
    violations = scan_content_fields(
        {
            "main_line1": "正常标题",
            "praise_tags": ["最好"],
        },
        registry=registry,
    )
    assert any(item.field == "praise_tags" for item in violations)
