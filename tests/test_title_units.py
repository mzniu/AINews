"""utils.title_units 汉字当量与截断"""
import pytest

from utils.title_units import (
    char_han_units,
    han_equiv_len,
    truncate_han_equiv,
    resolve_short_title,
    sanitize_short_title,
    MAIN_LINE1_MAX_UNITS,
    SHORT_TITLE_MAX_CHARS,
)


def test_ascii_half():
    assert char_han_units("A") == 0.5
    assert char_han_units("a") == 0.5
    assert char_han_units("9") == 0.5


def test_cjk_full():
    assert char_han_units("牛") == 1.0


def test_len_mixed():
    # 4 英文 = 2 + 2 汉字 = 2 => 4 当量
    assert han_equiv_len("AB你好") == pytest.approx(3.0)


def test_truncate_mixed():
    s = "A" * 40  # 20 当量（主标题第一行上限）
    assert len(truncate_han_equiv(s, MAIN_LINE1_MAX_UNITS)) == 40
    assert han_equiv_len(truncate_han_equiv(s, MAIN_LINE1_MAX_UNITS)) == 20.0


def test_resolve_short_title_prefers_explicit():
    assert resolve_short_title("视频号短标题", "更长的成片主标题可以到二十个字") == "视频号短标题"


def test_resolve_short_title_falls_back_to_main_line():
    long_title = "一二三四五六七八九十壹贰叁肆伍陆柒"
    assert resolve_short_title("", long_title) == long_title[:SHORT_TITLE_MAX_CHARS]


def test_sanitize_short_title_strips_punctuation():
    assert sanitize_short_title("GPT-4.5 来了！") == "GPT4点5 来了"
    assert sanitize_short_title("炸裂！突发？") == "炸裂突发"
    assert sanitize_short_title("修复率升到47%") == "修复率升到47"


def test_sanitize_short_title_counts_spaces_in_16_chars():
    text = ("甲" * 8) + " " + ("乙" * 8)
    assert len(text) == 17
    assert sanitize_short_title(text) == ("甲" * 8) + " " + ("乙" * 7)
    assert len(sanitize_short_title(text)) == 16


def test_resolve_short_title_sanitizes_explicit_value():
    assert resolve_short_title("DeepSeek-V3 发布！", "更长主标题") == "DeepSeekV3 发布"


def test_truncate_cjk():
    s = "一二三四五六七八九十壹贰叁"  # 13 字
    out = truncate_han_equiv(s, 12)
    assert len(out) == 12
    assert han_equiv_len(out) == 12.0
