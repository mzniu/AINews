from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "tests/fixtures/ifeng/detail_sample.html").read_text(encoding="utf-8")
m = re.search(r"var allData\s*=\s*(\{.*?\});\s*\n", html, re.S)
data = json.loads(m.group(1))
doc = data["docData"]
print("docData keys", list(doc.keys()))
for k in doc:
    v = doc[k]
    if isinstance(v, (str, int, float, bool)) or v is None:
        print(k, type(v), str(v)[:120] if v is not None else None)
    elif isinstance(v, (list, dict)):
        print(k, type(v), "len", len(v))
