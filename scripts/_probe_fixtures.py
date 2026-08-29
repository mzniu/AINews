from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

html = Path("tests/fixtures/sina/detail_k_sina.html").read_text(encoding="utf-8")
soup = BeautifulSoup(html, "lxml")
for script in soup.find_all("script", type="application/ld+json"):
    data = json.loads(script.string or "{}")
    graph = data.get("@graph") or [data]
    for node in graph:
        if node.get("@type") == "NewsArticle":
            print("title", node.get("headline"))
            print("body len", len(node.get("articleBody") or ""))
            print("desc", (node.get("description") or "")[:100])
