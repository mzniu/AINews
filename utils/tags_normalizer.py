"""
结构化标签归一化：把 LLM 返回的标签整理为固定 10 个结构化位。

被两套内容生成流程复用：
- api/routes/crawler_routes.py::generate_summary
- services/github_content_service.py::ContentAnalyzer
"""
import re
from typing import List

DEFAULT_STRUCTURED_TAGS: List[str] = [
    '#人工智能', '#AI应用', '#AI资讯', '#AIAgent', '#小牛说',
    '#科技前沿', '#大模型', '#效率工具', '#行业观察', '#技术趋势',
]


def normalize_structured_tags(tags_value) -> str:
    """将模型标签结果整理为固定 10 个结构化标签（空格分隔的字符串）。"""
    if isinstance(tags_value, list):
        raw_text = ' '.join(str(tag) for tag in tags_value)
    else:
        raw_text = str(tags_value or '')

    hashtag_matches = re.findall(r"#[^\s,，、；;。.]+", raw_text)
    raw = raw_text.replace('，', ' ').replace(',', ' ').replace('、', ' ')
    parts = hashtag_matches or re.split(r"\s+", raw.strip())

    tags: List[str] = []
    seen = set()
    for part in parts:
        tag = part.strip().strip('；;。.')
        if not tag:
            continue
        if not tag.startswith('#'):
            tag = f"#{tag.lstrip('#')}"
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    for tag in DEFAULT_STRUCTURED_TAGS:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    has_ip_tag = '#小牛说' in tags or '#小牛说AI' in tags
    if not has_ip_tag:
        tags.insert(4, '#小牛说')
    elif len(tags) >= 5 and tags[4] not in ('#小牛说', '#小牛说AI'):
        ip_tag = '#小牛说' if '#小牛说' in tags else '#小牛说AI'
        tags = [tag for tag in tags if tag != ip_tag]
        tags.insert(4, ip_tag)

    deduped: List[str] = []
    seen.clear()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
        if len(deduped) == 10:
            break
    return ' '.join(deduped)
