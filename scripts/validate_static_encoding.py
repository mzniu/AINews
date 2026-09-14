from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    issues: list[str] = []

    for path in STATIC.rglob("*"):
        if path.suffix not in {".html", ".js", ".css"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "\ufffd" in text:
            issues.append(f"{path.relative_to(ROOT)}: contains replacement char")
        if 'src=\\"' in text:
            issues.append(f"{path.relative_to(ROOT)}: escaped script src")

    pc = STATIC / "publish_center.html"
    if pc.exists():
        text = pc.read_text(encoding="utf-8")
        for match in re.finditer(r"[\u4e00-\u9fff]\?", text):
            line = text.count("\n", 0, match.start()) + 1
            issues.append(f"publish_center.html:{line}: suspicious Chinese+? corruption")

    if issues:
        print("Issues found:")
        for item in issues:
            print(f"  - {item}")
        return 1

    print("All static encoding checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
