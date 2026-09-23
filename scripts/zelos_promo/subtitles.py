"""Timed subtitles for the Zelos promo, burned into the template's summary band.

The text follows the source audio, with the three speech-recognition errors in
transcript.json corrected: 避缓 -> 闭环, 一道体系 -> 一套体系, 开成 -> 开城.
"""
from __future__ import annotations

import os
import subprocess

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

CANVAS_W = 1080
BAND_TOP = 1418          # just under the card (card bottom = 1398)
TEXT_X = 67              # matches the template's summary x
RULE_X = 49
SIZE = 42
LINE_H = 58
MAX_W = 940

TEXT = (244, 247, 250)
ACCENT = (75, 228, 255)

HIGHLIGHT = ("运力管理平台", "运营闭环", "拎包入驻", "开城")

SEGMENTS = [
    (0.00, 3.12, "九识自主开发了运力管理平台"),
    (3.12, 5.76, "从智能调度、灵活定价"),
    (5.76, 8.48, "到订单、车辆和结算"),
    (8.48, 13.60, "我们希望把无人运力运营中的关键环节真正串起来"),
    (13.60, 16.52, "形成一整套完整的运营闭环"),
    (16.52, 18.56, "而我们最终希望做到的"),
    (18.56, 22.52, "是让每一位加盟商都可以拎包入驻"),
    (22.52, 24.12, "合作伙伴进入之后"),
    (24.12, 27.44, "不需要再从零开始重新搭建一套体系"),
    (27.44, 30.32, "而是能够更快地开城、更快地运营"),
    (30.32, 32.32, "更快地进入自己的业务"),
    (32.32, 36.08, "我们希望把加盟无人运力这件事做得更简单"),
    (36.08, 39.80, "把这套经过规模化验证的无人驾驶能力"),
    (39.80, 43.08, "装进更多车型，也带进更多行业"),
]


def _split_highlight(line: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    i = 0
    while i < len(line):
        for kw in HIGHLIGHT:
            if line.startswith(kw, i):
                parts.append((kw, True))
                i += len(kw)
                break
        else:
            if parts and not parts[-1][1]:
                parts[-1] = (parts[-1][0] + line[i], False)
            else:
                parts.append((line[i], False))
            i += 1
    return parts


def _wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> list[str]:
    lines, current = [], ""
    for ch in text:
        if draw.textlength(current + ch, font=fnt) <= MAX_W or not current:
            current += ch
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines[:2]


def render_strip(text: str, path: str) -> int:
    fnt = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", SIZE)
    img = Image.new("RGBA", (CANVAS_W, LINE_H * 2 + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lines = _wrap(d, text, fnt)

    d.rectangle([RULE_X, 8, RULE_X + 4, 8 + LINE_H * len(lines) - 14], fill=(*ACCENT, 210))
    for i, line in enumerate(lines):
        x, y = TEXT_X, 8 + i * LINE_H
        for chunk, hot in _split_highlight(line):
            d.text((x + 2, y + 2), chunk, font=fnt, fill=(0, 0, 0, 150))
            d.text((x, y), chunk, font=fnt, fill=(*(ACCENT if hot else TEXT), 255))
            x += d.textlength(chunk, font=fnt)
    img.save(path)
    return len(lines)


def burn(src: str, dst: str, workdir: str) -> None:
    os.makedirs(workdir, exist_ok=True)
    inputs, filters = [], []
    for i, (start, end, text) in enumerate(SEGMENTS):
        png = os.path.join(workdir, f"sub{i:02d}.png")
        render_strip(text, png)
        inputs += ["-i", png]

    chain = "[0:v]"
    for i, (start, end, _) in enumerate(SEGMENTS):
        label = f"[v{i}]"
        filters.append(f"{chain}[{i + 1}:v]overlay=0:{BAND_TOP}:enable='between(t,{start},{end})'{label}")
        chain = label

    cmd = [
        FFMPEG, "-y", "-i", src, *inputs,
        "-filter_complex", ";".join(filters),
        "-map", chain, "-map", "0:a",
        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst,
    ]
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "ignore")[-2500:])
    print("burned:", dst, os.path.getsize(dst))


if __name__ == "__main__":
    ROOT = r"D:\git\AINews\data\zelos"
    burn(
        os.path.join(ROOT, "chronicle_raw.mp4"),
        os.path.join(ROOT, "zelos_promo_45s.mp4"),
        os.path.join(ROOT, "tmp", "subs"),
    )
