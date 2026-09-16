from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "static").glob("*.html"):
    text = path.read_text(encoding="utf-8")
    fixed = text.replace(
        'src=\\"/static/js/shared/app_nav.js',
        'src="/static/js/shared/app_nav.js',
    )
    if fixed != text:
        path.write_text(fixed, encoding="utf-8", newline="\n")
        print(f"fixed {path.name}")
