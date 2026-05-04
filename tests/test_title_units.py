"""utils.title_units 汉字当量与截断"""
import pytest

from utils.title_units import (
    char_han_units,
    han_equiv_len,
    truncate_han_equiv,
    MAIN_LINE1_MAX_UNITS,
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
    s = "A" * 36  # 18 当量（主标题第一行上限）
    assert len(truncate_han_equiv(s, MAIN_LINE1_MAX_UNITS)) == 36
    assert han_equiv_len(truncate_han_equiv(s, MAIN_LINE1_MAX_UNITS)) == 18.0


def test_truncate_cjk():
    s = "一二三四五六七八九十壹贰叁"  # 13 字
    out = truncate_han_equiv(s, 12)
    assert len(out) == 12
    assert han_equiv_len(out) == 12.0
