"""content_methodology 共享 prompt 模块测试"""

from utils.content_methodology import build_methodology_prompt_section


def test_build_methodology_prompt_includes_forbidden_words_constraint():
    from utils.content_methodology import build_methodology_prompt_section

    prompt = build_methodology_prompt_section(
        vmin=120,
        vmax=400,
        json_template='{"summary": "test"}',
    )
    assert "【禁限词与合规约束" in prompt
    assert "100%有效" in prompt
    assert "全网第一" in prompt
    assert "领导人姓名" in prompt
    assert "集赞" in prompt
    assert "须同时遵守上方【禁限词与合规约束】" in prompt
    assert "网友锐评" in prompt
    assert "必须以「网友：」开头" in prompt
    assert "感叹词开头" in prompt
    assert "突发！" in prompt
