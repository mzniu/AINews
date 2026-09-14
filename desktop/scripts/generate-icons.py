"""Generate AINews desktop + web icons from the lighthouse mark, drawn at native size."""
from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
TAURI_ICONS = ROOT / "desktop" / "src-tauri" / "icons"
STATIC_DIR = ROOT / "static"
NAVY = (10, 22, 40, 255)  # #0A1628
GOLD = (212, 168, 76, 255)  # #D4A84C
ICO_BMP_SIZES = (16, 24, 32, 48, 64, 128)
ICO_PNG_SIZES = (256,)


def _xy(size: int, x: float, y: float) -> tuple[int, int]:
    return (round(x * (size - 1)), round(y * (size - 1)))


def _width(size: int, frac: float, minimum: int = 1) -> int:
    return max(minimum, round(frac * size))


def render_icon(size: int, *, opaque: bool = False) -> Image.Image:
    del opaque  # corners stay transparent so Windows can show the rounded plate
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = max(3, round(size * 0.22))
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=NAVY)

    inset = max(1, round(size * 0.045))
    border = max(1, round(size * 0.028))
    inner_radius = max(1, radius - inset)
    draw.rounded_rectangle(
        (inset, inset, size - 1 - inset, size - 1 - inset),
        radius=inner_radius,
        outline=GOLD,
        width=border,
    )

    peak = _xy(size, 0.50, 0.30)
    left_foot_outer = _xy(size, 0.20, 0.86)
    left_foot_inner = _xy(size, 0.34, 0.86)
    right_foot_inner = _xy(size, 0.66, 0.86)
    right_foot_outer = _xy(size, 0.80, 0.86)
    left_crotch = _xy(size, 0.42, 0.62)
    right_crotch = _xy(size, 0.58, 0.62)
    inner_peak = _xy(size, 0.50, 0.42)

    draw.polygon(
        [
            peak,
            right_foot_outer,
            right_foot_inner,
            inner_peak,
            left_foot_inner,
            left_foot_outer,
        ],
        fill=GOLD,
    )
    draw.polygon([inner_peak, left_crotch, right_crotch], fill=NAVY)

    bar_y0 = round(0.56 * (size - 1))
    bar_y1 = max(bar_y0 + max(2, round(size * 0.075)), round(0.655 * (size - 1)))
    bar_x0 = round(0.22 * (size - 1))
    bar_x1 = round(0.78 * (size - 1))
    flare = max(1, round(size * 0.02))
    draw.polygon(
        [
            (bar_x0 + flare, bar_y0),
            (bar_x1 - flare, bar_y0),
            (bar_x1, bar_y1),
            (bar_x0, bar_y1),
        ],
        fill=GOLD,
    )

    if size >= 24:
        arc_w = _width(size, 0.028, 2)
        for frac in (0.20, 0.145):
            box = (
                round((0.50 - frac) * (size - 1)),
                round((0.12) * (size - 1)),
                round((0.50 + frac) * (size - 1)),
                round((0.12 + frac * 2) * (size - 1)),
            )
            draw.arc(box, start=210, end=265, fill=GOLD, width=arc_w)
            draw.arc(box, start=275, end=330, fill=GOLD, width=arc_w)

    return img


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _ico_dib(img: Image.Image) -> bytes:
    """32-bit BGRA XOR bitmap + 1-bit AND mask. Windows RC needs this for sizes < 256."""
    img = img.convert("RGBA")
    width, height = img.size
    pixels = img.load()
    xor = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            xor.extend((blue, green, red, alpha))
    row_bytes = ((width + 31) // 32) * 4
    and_mask = bytearray()
    for y in range(height - 1, -1, -1):
        row = bytearray(row_bytes)
        for x in range(width):
            if pixels[x, y][3] < 128:
                row[x // 8] |= 0x80 >> (x % 8)
        and_mask.extend(row)
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height * 2,
        1,
        32,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    return header + xor + and_mask


def save_png(path: Path, size: int, *, opaque: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    render_icon(size, opaque=opaque).save(path, format="PNG")


def save_ico(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[int, bytes]] = []
    for size in ICO_BMP_SIZES:
        entries.append((size, _ico_dib(render_icon(size))))
    for size in ICO_PNG_SIZES:
        entries.append((size, _png_bytes(render_icon(size))))
    offset = 6 + 16 * len(entries)
    chunks = [struct.pack("<HHH", 0, 1, len(entries))]
    payloads = []
    for size, payload in entries:
        stored = 0 if size >= 256 else size
        chunks.append(struct.pack("<BBBBHHII", stored, stored, 0, 0, 1, 32, len(payload), offset))
        payloads.append(payload)
        offset += len(payload)
    path.write_bytes(b"".join(chunks) + b"".join(payloads))


def main() -> None:
    save_ico(TAURI_ICONS / "icon.ico")
    save_png(TAURI_ICONS / "32x32.png", 32)
    save_png(TAURI_ICONS / "128x128.png", 128)
    save_png(TAURI_ICONS / "128x128@2x.png", 256)
    save_png(TAURI_ICONS / "icon.png", 512)
    save_ico(STATIC_DIR / "favicon.ico")
    save_png(STATIC_DIR / "favicon.png", 256)
    save_png(STATIC_DIR / "brand" / "ainews-mark.png", 128)
    print("Generated icons:")
    for p in [
        TAURI_ICONS / "icon.ico",
        TAURI_ICONS / "32x32.png",
        TAURI_ICONS / "128x128.png",
        TAURI_ICONS / "128x128@2x.png",
        TAURI_ICONS / "icon.png",
        STATIC_DIR / "favicon.ico",
        STATIC_DIR / "favicon.png",
        STATIC_DIR / "brand" / "ainews-mark.png",
    ]:
        print(f"  {p}")


if __name__ == "__main__":
    main()
