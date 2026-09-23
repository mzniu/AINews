"""Render an end-state frame for each graphic card and tile them for review."""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cards import CARDS, H, W  # noqa: E402

OUT = r"D:\git\AINews\data\zelos\preview\cards"
os.makedirs(OUT, exist_ok=True)

# time (within the card) at which every element is already on screen
END_T = {"a1": 5.2, "a2": 2.8, "c": 4.8, "b1": 3.6, "b2": 3.2}

imgs = []
for key, fn in CARDS.items():
    img = fn(END_T[key])
    img.save(os.path.join(OUT, f"{key}.png"))
    imgs.append(img)
    print("card", key, img.size)

cols, scale = 2, 0.52
tw, th = int(W * scale), int(H * scale)
rows = (len(imgs) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw + (cols + 1) * 12, rows * th + (rows + 1) * 12), (24, 26, 30))
for i, img in enumerate(imgs):
    r, c = divmod(i, cols)
    sheet.paste(img.resize((tw, th), Image.LANCZOS), (12 + c * (tw + 12), 12 + r * (th + 12)))
sheet.save(os.path.join(OUT, "sheet.png"))
print("sheet", sheet.size)
