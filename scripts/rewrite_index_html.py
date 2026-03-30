"""Rewrite static/index.html: external CSS/JS, fix stray lines, video modal inside body."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html_path = ROOT / "static" / "index.html"
lines = html_path.read_text(encoding="utf-8").splitlines(keepends=True)

out = []
# Lines 1-6 (indices 0-5)
out.extend(lines[0:6])
out.append('    <link rel="stylesheet" href="/static/css/index.css">\n')
# Skip inline <style>...</style> : file line 7-1240 -> indices 6-1239
# Keep from line 1241 (index 1240): <!-- 引用截图
out.extend(lines[1240:1242])  # comment + screenshot script
out.append("</head>\n")
out.append("<body>\n")

# Body: lines 1245-1549 (1-based) -> index 1244:1549 — original had <body> on 1244, we skip duplicate <body>
# Original 1244: <body> — we already wrote <body>, so start from 1245 (index 1244)
body_chunk = lines[1245:1549]
blob = "".join(body_chunk)
blob = blob.replace(
    """                    <h4>📝 选择和编辑文章内容</h4>
        let currentData = null;
        // selectedImages 改为对象数组：[{path, duration, type}]
        let selectedImages = [];

                    <div class="content-editor">""",
    """                    <h4>📝 选择和编辑文章内容</h4>
                    <div class="content-editor">""",
)
out.append(blob)

# Video modal (was after </html>): indices 4604-4627 -> 4603:4628
out.extend(lines[4603:4628])

out.append("\n")
out.append('    <script src="/static/js/index/state.js"></script>\n')
out.append('    <script src="/static/js/index/main.js"></script>\n')
out.append('    <script src="/static/js/index/modal.js"></script>\n')
out.append('    <script src="/static/js/index/init.js"></script>\n')
out.append("</body>\n</html>\n")

html_path.write_text("".join(out), encoding="utf-8")
print("written", html_path, "bytes", len("".join(out)))
