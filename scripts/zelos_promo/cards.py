"""Animated graphic cards for the Zelos chronicle promo.

Each card is rendered at the chronicle hero size (982x745) so it fills the
white card of the `chronicle_archive_tech_blue` template exactly, and uses the
same palette as the template so the card reads as part of the frame.
"""
from __future__ import annotations

import math
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

# The chronicle hero box is 982x745; H.264 needs an even height, so the cards
# are rendered one pixel taller and the cover fit trims it back.
W, H = 982, 746
FPS = 24

BG = (10, 20, 36)
GLOW = (27, 111, 156)
ACCENT = (75, 228, 255)
ACCENT_DIM = (31, 127, 166)
TEXT = (244, 247, 250)
MUTED = (139, 150, 168)
HI = (255, 236, 48)

FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


def bold(size: int) -> ImageFont.FreeTypeFont:
    return font(FONT_BOLD, size)


def reg(size: int) -> ImageFont.FreeTypeFont:
    return font(FONT_REG, size)


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def appear(t: float, start: float, dur: float = 0.38) -> float:
    """0..1 progress of an element appearing at `start`."""
    return ease_out((t - start) / dur) if t > start else 0.0


def blend(base: tuple[int, int, int], color: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    a = max(0.0, min(1.0, a))
    return tuple(round(base[i] + (color[i] - base[i]) * a) for i in range(3))  # type: ignore[return-value]


def backdrop() -> Image.Image:
    """Dark tech backdrop matching TechBackdrop.tsx (glow + faint grid + frame)."""
    img = Image.new("RGB", (W, H), BG)

    glow = Image.new("RGB", (W, H), BG)
    gd = ImageDraw.Draw(glow)
    cx, cy = W * 0.5, H * 0.42
    max_r = int(max(W, H) * 0.72)
    for i in range(max_r, 0, -6):
        a = (1 - i / max_r) ** 2 * 0.55
        gd.ellipse([cx - i, cy - i * 0.8, cx + i, cy + i * 0.8], fill=blend(BG, GLOW, a))
    img = Image.blend(img, glow, 0.85)

    d = ImageDraw.Draw(img, "RGBA")
    for i in range(0, W // 54 + 2):
        x = i * 54
        major = i % 4 == 0
        d.line([(x, 0), (x, H)], fill=(*(ACCENT if major else ACCENT_DIM), 26 if major else 16), width=1)
    for i in range(0, H // 48 + 2):
        y = i * 48
        major = i % 4 == 0
        d.line([(0, y), (W, y)], fill=(*(ACCENT if major else ACCENT_DIM), 26 if major else 16), width=1)

    return img


def header(img: Image.Image, eyebrow: str, title: str, *, title_size: int = 58) -> int:
    """Draw the standard card header, return the y where body content can start."""
    d = ImageDraw.Draw(img)
    d.text((60, 52), eyebrow, font=reg(26), fill=MUTED)
    d.text((60, 92), title, font=bold(title_size), fill=TEXT)
    y = 92 + title_size + 26
    d.rectangle([60, y, 60 + 120, y + 4], fill=ACCENT)
    return y + 34


def _footnote(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    f = reg(22)
    d.text((W - 60 - d.textlength(text, font=f), H - 62), text, font=f, fill=(90, 102, 118))


# --------------------------------------------------------------------------- A1

A1_ROWS = [
    ("01", "智能调度", 0.00),
    ("02", "灵活定价", 1.33),
    ("03", "订单", 2.64),
    ("04", "车辆", 3.58),
    ("05", "结算", 4.48),
]


def card_a1(t: float) -> Image.Image:
    """Capacity platform: the five links light up one by one, on the beat."""
    img = backdrop()
    header(img, "ZELOS · 自主开发", "运力管理平台")
    d = ImageDraw.Draw(img, "RGBA")

    top, step = 246, 88
    for i, (idx, label, at) in enumerate(A1_ROWS):
        y = top + i * step
        p = appear(t, at)
        d.line([(60, y + 62), (W - 60, y + 62)], fill=(*ACCENT_DIM, 60), width=1)
        if p <= 0:
            d.text((60, y + 8), idx, font=reg(30), fill=(52, 66, 84))
            continue
        dx = round((1 - p) * -28)
        a = p
        d.text((60 + dx, y + 8), idx, font=bold(30), fill=blend(BG, ACCENT, a))
        d.text((140 + dx, y), label, font=bold(46), fill=blend(BG, TEXT, a))
        d.line([(60, y + 62), (60 + (W - 120) * p, y + 62)], fill=(*ACCENT, 170), width=2)
        d.ellipse([W - 74, y + 22, W - 56, y + 40], fill=blend(BG, ACCENT, a))
    return img


# --------------------------------------------------------------------------- A2

A2_NODES = ["智能调度", "灵活定价", "订单", "车辆", "结算"]


def card_a2(t: float) -> Image.Image:
    """The loop closes: 运营闭环."""
    img = backdrop()
    d = ImageDraw.Draw(img, "RGBA")
    d.text((60, 52), "五个环节 串成一条链", font=reg(28), fill=MUTED)

    cx, cy, r = W // 2, 392, 182
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*ACCENT_DIM, 70), width=2)

    sweep = ease_out(t / 1.4) * 360
    if sweep > 0:
        d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + sweep, fill=ACCENT, width=7)

    fl = reg(27)
    for i, name in enumerate(A2_NODES):
        ang = -90 + i * 72
        rad = math.radians(ang)
        px, py = cx + r * math.cos(rad), cy + r * math.sin(rad)
        lit = sweep >= i * 72
        d.ellipse([px - 11, py - 11, px + 11, py + 11], fill=ACCENT if lit else (46, 60, 78))
        lx, ly = cx + (r + 48) * math.cos(rad), cy + (r + 48) * math.sin(rad)
        tw = d.textlength(name, font=fl)
        d.text((lx - tw / 2, ly - 17), name, font=fl, fill=blend(BG, TEXT if lit else MUTED, 1.0))

    p = appear(t, 1.5, 0.45)
    if p > 0:
        f = bold(78)
        label = "运营闭环"
        d.text((cx - d.textlength(label, font=f) / 2, cy - 50), label, font=f, fill=blend(BG, HI, p))
    return img


# --------------------------------------------------------------------------- C

C_ROWS = [("技术团队", 0.45), ("调度系统", 1.35), ("结算体系", 2.25), ("运维网络", 3.15)]


def card_c(t: float) -> Image.Image:
    """What the franchisee does NOT have to build."""
    img = backdrop()
    body = header(img, "加盟商省掉的四件事", "全都交给平台")
    d = ImageDraw.Draw(img, "RGBA")

    top, step = body + 18, 82
    for i, (label, at) in enumerate(C_ROWS):
        y = top + i * step
        f = bold(48)
        w = d.textlength(label, font=f)
        p = appear(t, at, 0.3)
        col = blend(TEXT, (124, 137, 154), p)
        d.text((60, y), label, font=f, fill=col)
        if p > 0:
            d.line([(56, y + 34), (56 + (w + 8) * p, y + 34)], fill=ACCENT, width=5)

    p = appear(t, 4.05, 0.45)
    if p > 0:
        f = bold(64)
        label = "＝ 拎包入驻"
        d.text((60, H - 132), label, font=f, fill=blend(BG, HI, p))
    return img


# --------------------------------------------------------------------------- B1

B1_ROWS = [("3万+", "台无人车在运营", 0.25), ("300+", "座城市常态化落地", 1.15), ("L4", "全球规模最大的无人驾驶车队", 2.05)]


def card_b1(t: float) -> Image.Image:
    """Scale proof."""
    img = backdrop()
    body = header(img, "截至目前", "已经跑出来的规模")
    d = ImageDraw.Draw(img, "RGBA")

    top, step = body + 20, 128
    for i, (num, label, at) in enumerate(B1_ROWS):
        y = top + i * step
        p = appear(t, at, 0.42)
        if p <= 0:
            continue
        dy = round((1 - p) * 18)
        fn = bold(78)
        d.text((60, y + dy), num, font=fn, fill=blend(BG, HI, p))
        nw = d.textlength(num, font=fn)
        d.text((60 + nw + 24, y + 30 + dy), label, font=reg(36), fill=blend(BG, TEXT, p))
        d.line([(60, y + 104), (W - 60, y + 104)], fill=(*ACCENT_DIM, 70), width=1)
    _footnote(img, "数据据九识官方及公开报道")
    return img


# --------------------------------------------------------------------------- B2

B2_MODELS = [("Z5", "通用之选"), ("Z5 Pro", "高载能效"), ("Z5 Lite", "轻量先锋"), ("Z5 Pro 冷藏", "冷链恒温")]
B2_SCENES = ["快递物流", "商超快销", "生鲜冷链", "园区场景"]


def card_b2(t: float) -> Image.Image:
    """More vehicle models, more industries."""
    img = backdrop()
    body = header(img, "Zelos Inside · 生态开放", "从一辆车 到一张网", title_size=52)
    d = ImageDraw.Draw(img, "RGBA")

    col_w = (W - 120 - 40) // 2
    lx, rx = 60, 60 + col_w + 40
    d.text((lx, body + 8), "车型", font=reg(28), fill=ACCENT)
    d.text((rx, body + 8), "行业", font=reg(28), fill=ACCENT)

    top, step = body + 62, 88
    for i, (name, tag) in enumerate(B2_MODELS):
        y = top + i * step
        p = appear(t, 0.15 + i * 0.16, 0.34)
        if p <= 0:
            continue
        dx = round((1 - p) * -20)
        d.text((lx + dx, y), name, font=bold(44), fill=blend(BG, TEXT, p))
        d.text((lx + dx, y + 52), tag, font=reg(26), fill=blend(BG, MUTED, p))

    for i, scene in enumerate(B2_SCENES):
        y = top + i * step
        p = appear(t, 0.9 + i * 0.16, 0.34)
        if p <= 0:
            continue
        dx = round((1 - p) * 20)
        d.line([(rx + dx, y + 6), (rx + dx, y + 50)], fill=(*ACCENT, 200), width=4)
        d.text((rx + 22 + dx, y), scene, font=bold(42), fill=blend(BG, TEXT, p))
    return img


CARDS: dict[str, Callable[[float], Image.Image]] = {
    "a1": card_a1,
    "a2": card_a2,
    "c": card_c,
    "b1": card_b1,
    "b2": card_b2,
}
