"""Pull key frames out of a render and tile them for review."""
import os
import subprocess
import sys

import imageio_ffmpeg
from PIL import Image

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
src = sys.argv[1]
out_dir = sys.argv[2]
times = [float(t) for t in sys.argv[3].split(",")]
os.makedirs(out_dir, exist_ok=True)

imgs = []
for t in times:
    dst = os.path.join(out_dir, f"t{t:05.1f}.png")
    subprocess.run([FFMPEG, "-y", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", dst], capture_output=True)
    imgs.append((t, Image.open(dst)))
    print("frame", t)

cols = 5
scale = 0.24
tw, th = int(1080 * scale), int(1920 * scale)
rows = (len(imgs) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * th + (rows + 1) * 8), (20, 22, 26))
for i, (t, img) in enumerate(imgs):
    r, c = divmod(i, cols)
    sheet.paste(img.convert("RGB").resize((tw, th), Image.LANCZOS), (8 + c * (tw + 8), 8 + r * (th + 8)))
path = os.path.join(out_dir, "sheet.png")
sheet.save(path)
print("sheet", path, sheet.size)
