"""Sample the source clip every second to map its shot changes."""
import os
import subprocess

import imageio_ffmpeg
from PIL import Image

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SRC = r"D:\git\AINews\data\zelos\source.mp4"
OUT = r"D:\git\AINews\data\zelos\preview\shots"
os.makedirs(OUT, exist_ok=True)

times = [t for t in range(0, 44)]
imgs = []
for t in times:
    dst = os.path.join(OUT, f"s{t:02d}.jpg")
    subprocess.run([FFMPEG, "-y", "-ss", str(t), "-i", SRC, "-frames:v", "1", "-q:v", "4", dst], capture_output=True)
    imgs.append((t, Image.open(dst)))

cols, tw = 8, 180
th = round(tw * 736 / 720)
rows = (len(imgs) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw, rows * th), (0, 0, 0))
for i, (t, img) in enumerate(imgs):
    r, c = divmod(i, cols)
    sheet.paste(img.convert("RGB").resize((tw, th), Image.LANCZOS), (c * tw, r * th))
sheet.save(os.path.join(OUT, "sheet.jpg"), quality=88)
print("tiles:", len(imgs), "grid:", cols, "x", rows, "(t=0..43, 1s step, row-major)")
