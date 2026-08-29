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


# 主标题第一行：上限 20 汉字当量（产品「12～16」由 AI 控制，服务端防超长）
MAIN_LINE1_MAX_UNITS = 20.0
# 主标题第二行：上限 12 汉字当量（产品「9～12」）
MAIN_LINE2_MAX_UNITS = 12.0
# 视频号短标题：最多 16 个字符（含空格），不含标点
SHORT_TITLE_MAX_CHARS = 16
SHORT_TITLE_MAX_UNITS = float(SHORT_TITLE_MAX_CHARS)
# 兼容旧代码：曾统一用 14；新逻辑请用 MAIN_LINE1_MAX_UNITS / MAIN_LINE2_MAX_UNITS
MAIN_LINE_MAX_UNITS = MAIN_LINE1_MAX_UNITS
# 副标题第一行上限 15 汉字当量（产品「11～15」）
SUBTITLE_MAX_UNITS = 15.0
# 副标题第二行（流量钩子）上限 15 汉字当量（产品「11～15」，与 sub_title 同上限）
SUBTITLE2_MAX_UNITS = 15.0


def split_main_title_to_two_lines(title: str) -> tuple[str, str]:
    """
    与主页 index 一致：主标题拆成两行；第一行不超过 MAIN_LINE1_MAX_UNITS、
    第二行不超过 MAIN_LINE2_MAX_UNITS 汉字当量。
    优先按换行；否则超长时在逗号等弱标点处拆，再按当量中分。
    """
    title = (title or "").strip()
    if not title:
        return "", ""
    if "\n" in title:
        a, b = title.split("\n", 1)
        return (
            truncate_han_equiv(a.strip(), MAIN_LINE1_MAX_UNITS),
            truncate_han_equiv(b.strip(), MAIN_LINE2_MAX_UNITS),
        )
    if han_equiv_len(title) <= MAIN_LINE1_MAX_UNITS:
        return truncate_han_equiv(title, MAIN_LINE1_MAX_UNITS), ""
    # 超过一行：按当量中点附近优先在弱标点处断开
    total_u = han_equiv_len(title)
    target_u = total_u / 2.0
    acc = 0.0
    break_idx: int | None = None
    for i, ch in enumerate(title):
        acc += char_han_units(ch)
        if acc >= target_u:
            if ch in "，,、；： ":
                break_idx = i + 1
                break
            if break_idx is None:
                break_idx = i + 1
    if break_idx is None:
        break_idx = max(1, len(title) // 2)
    line1 = truncate_han_equiv(title[:break_idx].strip(), MAIN_LINE1_MAX_UNITS)
    line2 = truncate_han_equiv(title[break_idx:].strip(), MAIN_LINE2_MAX_UNITS)
    return line1, line2


def sanitize_short_title(text: str, *, max_chars: int = SHORT_TITLE_MAX_CHARS) -> str:
    """Keep letters, digits, CJK and spaces; turn '.' into 点; drop other punctuation."""
    kept: list[str] = []
    for ch in text or "":
        if ch in ".-．。":
            if ch in ".．。":
                kept.append("点")
            continue
        if ch == " " or ch.isalnum():
            kept.append(ch)
    cleaned = " ".join("".join(kept).split())
    return cleaned[: max(0, int(max_chars))]


def resolve_short_title(
    short_title: str,
    main_line1: str = "",
    *,
    max_units: float = SHORT_TITLE_MAX_UNITS,
    max_chars: int | None = None,
) -> str:
    """Prefer an explicit short title; otherwise compress the on-video main title."""
    limit = SHORT_TITLE_MAX_CHARS if max_chars is None else int(max_chars)
    if max_chars is None and max_units != SHORT_TITLE_MAX_UNITS:
        limit = int(max_units)
    text = (short_title or "").strip() or (main_line1 or "").strip()
    return sanitize_short_title(text, max_chars=limit)


def format_main_title_two_lines(title: str) -> str:
    """与成片一致：主标题拆成两行后用 \\n 拼接，供 API 与第三步编辑区展示。"""
    a, b = split_main_title_to_two_lines((title or "").strip())
    return f"{a}\n{b}" if b else a
