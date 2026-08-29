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
    assert "没有争议钩子" in prompt or "无争议钩子" in prompt
    assert "12-16" in prompt or "12～16" in prompt
    assert "摘要" in prompt
    assert "人物钩子" in prompt or "ChatGPT" in prompt
    assert "16" in prompt
    assert "标点" in prompt
    assert "必须以感叹词开头" not in prompt
    assert "55-65 字" in prompt
    assert "前3秒" in prompt or "前 3 秒" in prompt
    assert "不要以「小牛说」开头" in prompt or "不要以「小牛说：" in prompt
    assert "可回答的争议" in prompt or "评论开口" in prompt
    assert "点赞关注" in prompt
