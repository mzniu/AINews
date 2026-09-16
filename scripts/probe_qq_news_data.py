"""Inspect window.DATA from Tencent article page."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

html = (ROOT / "tests/fixtures/qq_news/detail_sample.html").read_text(encoding="utf-8")
m = re.search(r"window\.DATA\s*=\s*(\{.*?\});\s*\n", html, re.S)
if not m:
    m = re.search(r"window\.DATA\s*=\s*(\{.*\})\s*;?\s*</script>", html, re.S)
print("match", bool(m), "len", len(m.group(1)) if m else 0)
data = json.loads(m.group(1))
print("top keys", list(data.keys())[:20])
# find content fields
for key in ["content", "originContent", "text", "article", "articleContent"]:
    if key in data:
        print(key, str(data[key])[:200])

def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k in {"content", "originContent", "text", "abstract", "intro", "title", "time"}:
                print(p, type(v), str(v)[:120])
            if len(path.split(".")) < 4:
                walk(v, p)
    elif isinstance(obj, list) and obj and len(path.split(".")) < 4:
        walk(obj[0], path + "[0]")

walk(data)
