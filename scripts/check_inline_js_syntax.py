from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def extract_scripts(html: str) -> list[str]:
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, flags=re.S | re.I)


def main() -> int:
    html_path = ROOT / "static" / "publish_center.html"
    html = html_path.read_text(encoding="utf-8")
    scripts = extract_scripts(html)
    if not scripts:
        print("No inline scripts found.")
        return 1

    for index, script in enumerate(scripts, start=1):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(script)
            tmp_path = tmp.name
        result = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            text=True,
        )
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        if result.returncode != 0:
            print(f"Script block {index} failed syntax check:")
            print(result.stderr.strip() or result.stdout.strip())
            return 1
        print(f"Script block {index}: OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
