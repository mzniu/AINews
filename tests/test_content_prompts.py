"""Title-generation prompt config: YAML defaults + local overrides."""
from __future__ import annotations

import yaml

from services.content_prompts import (
    get_system_role,
    get_title_prompts,
    json_main_line1_hint,
    json_short_title_hint,
    json_summary_hint,
    reset_title_prompts,
    save_title_prompts,
)
from utils.content_methodology import build_methodology_prompt_section


def _patch_paths(tmp_path, monkeypatch, *, base: dict, local: dict | None = None):
    base_path = tmp_path / "content_prompts.yaml"
    local_path = tmp_path / "content_prompts.local.yaml"
    base_path.write_text(yaml.dump(base, allow_unicode=True), encoding="utf-8")
    if local is not None:
        local_path.write_text(yaml.dump(local, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr("services.content_prompts.PROMPTS_BASE_PATH", base_path)
    monkeypatch.setattr("services.content_prompts.PROMPTS_LOCAL_PATH", local_path)
    return base_path, local_path


def test_default_title_prompt_forbids_hype_and_requires_facts():
    prompts = get_title_prompts()
    blob = "\n".join(prompts.values())
    assert "事实抓眼" in blob
    assert "禁止" in blob and "误导" in blob
    assert "必须以感叹词开头" not in blob
    assert "炸裂！" in blob  # mentioned as forbidden example
    assert json_main_line1_hint()
    assert "夸张" in json_main_line1_hint() or "误导" in json_main_line1_hint()
    assert "12" in json_main_line1_hint() and "16" in json_main_line1_hint()
    assert "摘要" in prompts["main_line1_patterns"]
    assert "ChatGPT" in prompts["main_line1_patterns"] or "人物钩子" in prompts["main_line1_patterns"]
    assert json_short_title_hint()
    assert "短标题" in json_short_title_hint() or "视频号" in json_short_title_hint()
    assert "单独成句" in json_short_title_hint() or "单独成句" in prompts["short_title_patterns"]
    assert prompts["short_title_patterns"]
    assert "小牛说" in prompts["summary_patterns"] or "摘要" in prompts["summary_patterns"]
    assert "summary" in prompts["stage2_summary"].lower() or "摘要" in prompts["stage2_summary"]
    assert json_summary_hint()
    assert "摘要" in json_summary_hint()
    assert "感叹" in get_system_role() or "事实" in get_system_role()
    assert "炸裂" in get_system_role() or "禁止" in get_system_role()
    assert "争议" in prompts["content_formula"] or "可空" in prompts["content_formula"]


def test_methodology_prompt_uses_factual_title_rules():
    prompt = build_methodology_prompt_section(
        vmin=70,
        vmax=90,
        json_template='{"summary": "test"}',
    )
    assert "事实抓眼" in prompt
    assert "必须以感叹词开头" not in prompt
    assert "100-130 字" in prompt
    assert "网友锐评" in prompt
    assert "没有争议钩子" in prompt or "无争议钩子" in prompt
    assert "12-16" in prompt or "12～16" in prompt
    assert "摘要" in prompt
    assert "人物钩子" in prompt or "ChatGPT" in prompt
    assert "前3秒" in prompt or "前 3 秒" in prompt
    assert "不要以「小牛说」开头" in prompt or "不要以「小牛说：" in prompt
    assert "可回答的争议" in prompt or "评论开口" in prompt
    assert "观众想看看真假" in prompt
    assert prompt.index("观众想看看真假") < prompt.index("观众想看结果")
    assert "点赞关注" in prompt
    assert "抖音" in prompt and "标点" in prompt


def test_local_override_appears_in_methodology_prompt(tmp_path, monkeypatch):
    _patch_paths(
        tmp_path,
        monkeypatch,
        base={
            "title": {
                "system_role": "默认角色",
                "content_formula": "默认公式",
                "main_line1_patterns": "默认主标题规则",
                "stage2_main_line1": "1. 默认字段",
                "stage2_short_title": "2. 默认短标题",
                "stage2_summary": "6. 默认摘要规则",
                "json_main_line1_hint": "默认hint",
                "json_short_title_hint": "默认短标题hint",
                "json_summary_hint": "默认摘要hint",
            }
        },
        local={"title": {"main_line1_patterns": "本地覆盖：只用数字写标题"}},
    )
    prompt = build_methodology_prompt_section(
        vmin=40,
        vmax=80,
        json_template="{}",
    )
    assert "本地覆盖：只用数字写标题" in prompt
    assert "默认主标题规则" not in prompt
    assert get_title_prompts()["content_formula"] == "默认公式"


def test_summary_prompt_override_appears_in_methodology_prompt(tmp_path, monkeypatch):
    _patch_paths(
        tmp_path,
        monkeypatch,
        base={
            "title": {
                "system_role": "默认角色",
                "content_formula": "默认公式",
                "main_line1_patterns": "默认主标题规则",
                "stage2_main_line1": "1. 默认字段",
                "stage2_short_title": "2. 默认短标题",
                "stage2_summary": "6. 默认摘要规则",
                "json_main_line1_hint": "默认hint",
                "json_short_title_hint": "默认短标题hint",
                "json_summary_hint": "默认摘要hint",
            }
        },
        local={"title": {"summary_patterns": "本地覆盖：摘要必须更短更狠"}},
    )
    prompt = build_methodology_prompt_section(
        vmin=40,
        vmax=80,
        json_template="{}",
    )
    assert "本地覆盖：摘要必须更短更狠" in prompt
    assert get_title_prompts()["stage2_summary"] == "6. 默认摘要规则"


def test_save_and_reset_title_prompts(tmp_path, monkeypatch):
    _base, local_path = _patch_paths(
        tmp_path,
        monkeypatch,
        base={
            "title": {
                "system_role": "默认角色",
                "content_formula": "默认公式",
                "main_line1_patterns": "默认主标题规则",
                "stage2_main_line1": "1. 默认字段",
                "stage2_short_title": "2. 默认短标题",
                "stage2_summary": "6. 默认摘要规则",
                "json_main_line1_hint": "默认hint",
                "json_short_title_hint": "默认短标题hint",
                "json_summary_hint": "默认摘要hint",
            }
        },
    )
    saved = save_title_prompts({"main_line1_patterns": "  新规则  "})
    assert saved["main_line1_patterns"] == "新规则"
    assert local_path.exists()
    reset = reset_title_prompts()
    assert reset["main_line1_patterns"] == "默认主标题规则"


def test_json_summary_hint_syncs_with_stage2_length(tmp_path, monkeypatch):
    _patch_paths(
        tmp_path,
        monkeypatch,
        base={
            "title": {
                "system_role": "默认角色",
                "content_formula": "默认公式",
                "main_line1_patterns": "默认主标题规则",
                "stage2_main_line1": "1. 默认字段",
                "stage2_short_title": "2. 默认短标题",
                "stage2_summary": "6. summary（摘要）：55-65 字。",
                "json_main_line1_hint": "默认hint",
                "json_short_title_hint": "默认短标题hint",
                "json_summary_hint": "生成的摘要（55-65字，以「小牛说：」开头）",
            }
        },
    )
    save_title_prompts(
        {
            "stage2_summary": "6. summary（摘要）：100-130 字。以「小牛说：」开头。",
            "summary_patterns": "- 100-130 字，必须以「小牛说：」开头",
        }
    )
    assert "100-130字" in json_summary_hint()
