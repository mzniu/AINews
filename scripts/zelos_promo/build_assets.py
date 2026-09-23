"""Build every asset the Zelos chronicle promo needs, then write Remotion props.

Outputs land in remotion/public/runtime/zelos/ so `staticFile()` can resolve
them, and the props JSON drives the `ChronicleVideo` composition.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cards import CARDS, FPS, H, W  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = r"D:\git\AINews"
SRC = os.path.join(ROOT, "data", "zelos", "source.mp4")
OUT = os.path.join(ROOT, "remotion", "public", "runtime", "zelos")
TMP = os.path.join(ROOT, "data", "zelos", "tmp")

# Frame-aligned edit. Boundaries are chosen so every cut lands on a beat of the
# speech, and so the source segments stay in sync with the untouched audio bed.
EDIT = [
    ("src", 0, 75),        # 讲者出场（背景大屏正好是"智能调度"）
    ("a1", 75, 204),       # 五个环节随语音依次点亮
    ("src", 204, 326),     # "把关键环节真正串起来"
    ("a2", 326, 396),      # 闭环合拢
    ("src", 396, 540),     # 金句："让每一位加盟商都可以拎包入住"
    ("c", 540, 659),       # 不必从零搭一套体系
    ("src", 659, 866),     # "更快地开城、更快地运营"
    ("b1", 866, 955),      # 规模化验证的数据
    ("b2", 955, 1034),     # 更多车型、更多行业
    ("src", 1034, 1093),   # 片尾自带的 ZELOS logo 卡
]


def run(cmd: list[str]) -> None:
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "ignore")[-2000:])


def build_audio() -> str:
    """Original speech, loudness-normalised, as the single audio bed."""
    dst = os.path.join(OUT, "audio.wav")
    run([
        FFMPEG, "-y", "-i", SRC, "-vn",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst,
    ])
    print("audio:", dst, os.path.getsize(dst))
    return dst


def build_source_clip(index: int, start_f: int, end_f: int) -> str:
    """Crop 720x736 -> the card's 982x745 and cut the exact frame range."""
    dst = os.path.join(OUT, f"src{index:02d}.mp4")
    start = start_f / FPS
    frames = end_f - start_f
    vf = (
        "crop=720:547:0:94,"  # 720x736 -> the card's aspect, trimming empty headroom and legs
        f"scale={W}:{H}:flags=lanczos,"
        "unsharp=5:5:0.45:5:5:0.0,"
        "tpad=stop_mode=clone:stop_duration=1"
    )
    run([
        FFMPEG, "-y", "-ss", f"{start:.4f}", "-i", SRC,
        "-vf", vf, "-frames:v", str(frames), "-r", str(FPS),
        "-an", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
        "-pix_fmt", "yuv420p", dst,
    ])
    print(f"src{index:02d}: {start:.3f}s +{frames}f -> {os.path.getsize(dst)}")
    return dst


def build_card_clip(key: str, index: int, frames: int) -> str:
    """Render the animated graphic card frame by frame."""
    frame_dir = os.path.join(TMP, key)
    shutil.rmtree(frame_dir, ignore_errors=True)
    os.makedirs(frame_dir, exist_ok=True)
    fn = CARDS[key]
    for f in range(frames):
        fn(f / FPS).save(os.path.join(frame_dir, f"{f:05d}.png"))

    dst = os.path.join(OUT, f"card{index:02d}_{key}.mp4")
    run([
        FFMPEG, "-y", "-framerate", str(FPS), "-i", os.path.join(frame_dir, "%05d.png"),
        "-frames:v", str(frames), "-c:v", "libx264", "-crf", "16", "-preset", "slow",
        "-pix_fmt", "yuv420p", dst,
    ])
    print(f"card {key}: {frames}f -> {os.path.getsize(dst)}")
    return dst


DRAFT = {
    "main_line1": "从卖车 到卖运力",
    "main_line2": "九识开放城市无人运力加盟",
    "sub_title": "L4 RoboVan · 300+城市 · 3万台",
    # 「拎包入驻」is the wording on Zelos' own stage slide, so the frame matches it.
    "sub_title2": "拎包入驻：不用建团队 不用搭系统",
    "summary": "",  # the band below the card carries timed subtitles instead
    "tags": "",
    "highlight_keywords": ["卖运力", "加盟"],
}


def build_props(clips: list[dict]) -> str:
    import yaml

    with open(os.path.join(ROOT, "config", "render_templates.yaml"), encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    template = next(t for t in cfg["templates"] if t["id"] == "chronicle_archive_tech_blue")

    # A talking head must not drift or soften, so the Ken Burns pass is off and
    # the motion is baked into the graphic cards instead.
    template["video"]["card_motion"] = {"enabled": False}
    template["video"]["show_summary"] = False
    template["video"]["summary_animation"] = {"mode": "none"}
    template["chrome"]["footer_left"] = "AI 快讯 ｜ 品牌合作内容"

    props = {
        "articleId": "zelos",
        "draft": DRAFT,
        "images": clips,
        "audioPath": "runtime/zelos/audio.wav",
        "template": template,
        "seed": "zelos",
    }
    dst = os.path.join(ROOT, "data", "zelos", "props.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(props, fh, ensure_ascii=False, indent=2)
    print("props:", dst)
    return dst


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    build_audio()

    clips = []
    for i, (kind, start_f, end_f) in enumerate(EDIT):
        frames = end_f - start_f
        if kind == "src":
            path = build_source_clip(i, start_f, end_f)
        else:
            path = build_card_clip(kind, i, frames)
        clips.append({
            "path": f"runtime/zelos/{os.path.basename(path)}",
            "duration": frames / FPS,
        })

    total = sum(c["duration"] for c in clips)
    print(f"total: {total:.4f}s / {round(total * FPS)}f")
    build_props(clips)


if __name__ == "__main__":
    main()
