"""摘要画面高亮关键字：合并标签 / 显式词，并由大模型在摘要中选出 3～5 个可匹配子串。"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from loguru import logger

from utils.video_utils import merge_summary_highlight_keywords

# 成片摘要高亮：中文等一般不超过此字数（len）；纯英文单词按「整词」计，不按本数字截断
HIGHLIGHT_KEYWORD_MAX_CHARS = 5

_RE_SINGLE_ASCII_WORD = re.compile(r"^[A-Za-z]+$")
_RE_LEADING_ASCII_RUN = re.compile(r"^([A-Za-z]+)")


def is_single_ascii_word(s: str) -> bool:
    """仅由英文字母组成的单个单词（整词高亮，不按 HIGHLIGHT_KEYWORD_MAX_CHARS 截断）。"""
    s = (s or "").strip()
    return bool(s and _RE_SINGLE_ASCII_WORD.match(s))


def _ends_mid_ascii_word(prefix: str, k: str) -> bool:
    """prefix 为 k 的前缀，且截断位置落在同一 ASCII 字母连续段中间。"""
    n = len(prefix)
    if n == 0 or n >= len(k):
        return False
    a, b = prefix[-1], k[n]
    return bool(a.isascii() and a.isalpha() and b.isascii() and b.isalpha())


def fit_keyword_for_summary(k: str, summary: str, max_chars: int = HIGHLIGHT_KEYWORD_MAX_CHARS) -> Optional[str]:
    """
    将关键字收束为摘要中仍存在的连续子串。
    - 纯英文单词（仅 A–Z）：整词为一个 keyword，不因 5 字限制从中间截断。
    - 中文等：一般不超过 max_chars（每字 len 为 1）。
    - 混合或短语：需要缩短时，不在英文单词中间截断（避免只高亮半个单词）。
    """
    k = (k or "").strip()
    if not k or not summary:
        return None
    if k not in summary:
        return None
    if is_single_ascii_word(k):
        return k
    if len(k) <= max_chars:
        return k
    # 开头一段连续英文后接非字母（或空格）：整段英文作为一个 keyword（可长于 max_chars）
    m = _RE_LEADING_ASCII_RUN.match(k)
    if m:
        w = m.group(1)
        rest = k[len(w) :]
        if w in summary and (
            not rest
            or not (rest[0].isascii() and rest[0].isalpha())
        ):
            return w
    for L in range(max_chars, 0, -1):
        prefix = k[:L]
        if prefix not in summary:
            continue
        if _ends_mid_ascii_word(prefix, k):
            continue
        return prefix
    return None


def finalize_highlight_keywords(keywords: List[str], summary: str) -> List[str]:
    """去重、长度限制、必须仍在摘要中可匹配。"""
    if not summary:
        return []
    seen = set()
    out: List[str] = []
    for k in keywords:
        fitted = fit_keyword_for_summary(k, summary, HIGHLIGHT_KEYWORD_MAX_CHARS)
        if fitted and fitted not in seen:
            seen.add(fitted)
            out.append(fitted)
    return out[:5]


def normalize_highlight_keywords_from_llm(raw, summary: str) -> List[str]:
    """过滤为摘要中真实子串，去重，最多 5 个；中文等经 fit 收束；英文整词不截半。"""
    if not summary:
        return []
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("["):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = []
        else:
            raw = []
    if not isinstance(raw, (list, tuple)):
        return []
    out: List[str] = []
    for k in raw:
        s = str(k).strip()
        if s and s in summary:
            out.append(s)
    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return finalize_highlight_keywords(uniq, summary)


def pick_highlight_keywords_llm(
    summary: str,
    tags: Optional[str],
    hints: List[str],
) -> List[str]:
    """调用 DeepSeek，在摘要中选出 3～5 个连续子串；失败返回 []。"""
    summary = (summary or "").strip()
    if not summary:
        return []
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key_here":
        return []
    try:
        from openai import OpenAI
    except ImportError:
        return []

    tags = tags or ""
    hints_str = "、".join(hints[:30]) if hints else "（无）"
    prompt = f"""请为下面「摘要」挑选 3～5 个用于画面文字高亮的词或短语。

硬性要求：
- 每一项必须是摘要原文中的连续子串（与摘要中的文字完全一致，不可改写、不可编造）。
- 中文或中英混合里的「词」：每一项不超过 {HIGHLIGHT_KEYWORD_MAX_CHARS} 个字符（汉字、字母均按 1 个计），优先短词。
- 若某项是纯英文单词（仅字母），则整词作为一个高亮项，不要截断到 5 个字母。
- 优先从「标签」与「候选词」中选取在摘要里出现的词；若不足 3 个，再从摘要里补充信息量高、适合加粗强调的词。
- 输出 3～5 个字符串，不要重复，不要输出摘要中不存在的词。

摘要：
{summary}

标签（供参考，去掉 # 后若在摘要中出现可优先）：
{tags}

候选词（已部分从标签合并，在摘要中出现的请优先用）：
{hints_str}

只返回 JSON 对象：{{"highlight_keywords": ["词1", "词2", ...]}}"""

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        response = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你只输出合法 JSON。highlight_keywords 中每个词必须是用户摘要里连续出现的原文。"
                        f"中文等非英文片段每个不超过 {HIGHLIGHT_KEYWORD_MAX_CHARS} 个字符；"
                        "纯英文单词请整词输出，不要截断。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content.strip()
        data = json.loads(text)
        raw = data.get("highlight_keywords") or data.get("keywords") or []
        return normalize_highlight_keywords_from_llm(raw, summary)
    except Exception as e:
        logger.warning(f"pick_highlight_keywords_llm 失败: {e}")
        return []


def resolve_highlight_keywords(
    summary: str,
    tags: Optional[str],
    explicit: Optional[List[str]],
) -> List[str]:
    """
    合并标签与显式词（含生成摘要接口返回的 highlight_keywords）。
    若已有 3～5 个且均在摘要中，直接使用以省一次大模型调用；
    否则调用大模型，结合标签与候选词选出 3～5 个。
    """
    summary = (summary or "").strip()
    if not summary:
        return []

    merged = merge_summary_highlight_keywords(list(explicit or []), tags or "")
    valid_explicit = finalize_highlight_keywords(
        [k for k in (explicit or []) if k and k in summary],
        summary,
    )
    if 3 <= len(valid_explicit) <= 5:
        return valid_explicit

    llm_kw = pick_highlight_keywords_llm(summary, tags, merged)
    if llm_kw and len(llm_kw) >= 3:
        return finalize_highlight_keywords(llm_kw, summary)

    in_summary = finalize_highlight_keywords(
        [k for k in merged if k and k in summary],
        summary,
    )
    if llm_kw:
        combined = merge_summary_highlight_keywords(llm_kw + in_summary, None)
        combined = [k for k in combined if k in summary]
        seen = set()
        out: List[str] = []
        for k in combined:
            if k not in seen:
                seen.add(k)
                out.append(k)
        fin = finalize_highlight_keywords(out, summary)
        if len(fin) >= 3:
            return fin
    return in_summary
