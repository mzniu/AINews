"""标题长度：汉字计 1，英文字母与数字计 0.5（半个汉字）。"""
from __future__ import annotations


def char_han_units(ch: str) -> float:
    if not ch:
        return 0.0
    o = ord(ch)
    if (48 <= o <= 57) or (65 <= o <= 90) or (97 <= o <= 122):
        return 0.5
    # CJK 统一表意文字及扩展 A 等常见区
    if 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF:
        return 1.0
    # 其余标点、空格等按 1 字计，避免过长
    return 1.0


def han_equiv_len(s: str) -> float:
    return sum(char_han_units(c) for c in s)


def truncate_han_equiv(s: str, max_units: float) -> str:
    """按汉字当量截断，不超过 max_units。"""
    if not s:
        return ""
    acc = 0.0
    out = []
    for ch in s:
        u = char_han_units(ch)
        if acc + u <= max_units + 1e-9:
            out.append(ch)
            acc += u
        else:
            break
    return "".join(out)


# 主标题每行：上限 14 汉字当量（产品「12～14」由 AI 控制，服务端防超长）
MAIN_LINE_MAX_UNITS = 14.0
# 副标题单行上限 16 汉字当量（产品「14～16」）
SUBTITLE_MAX_UNITS = 16.0
