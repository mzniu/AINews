"""One-off extract CSS/JS from static/index.html — run from repo root: python scripts/extract_index_assets.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = ROOT / "static" / "index.html"
lines = html.read_text(encoding="utf-8").splitlines(keepends=True)

css_raw = lines[7:1239]
css_out = "".join(s[8:] if s.startswith("        ") else s for s in css_raw)
(ROOT / "static" / "css").mkdir(parents=True, exist_ok=True)
(ROOT / "static" / "css" / "index.css").write_text(css_out, encoding="utf-8")

js_inner = lines[1550:4600]  # through closing `});` of last listener (line 4600)
js_text = "".join(js_inner)
(ROOT / "static" / "js" / "index").mkdir(parents=True, exist_ok=True)
(ROOT / "static" / "js" / "index" / "_full.js").write_text(js_text, encoding="utf-8")
print("OK", len(css_out), len(js_inner))
