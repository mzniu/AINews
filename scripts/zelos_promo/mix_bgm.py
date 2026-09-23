"""Mix low-volume BGM under the Zelos promo speech track."""
from __future__ import annotations

import os
import subprocess

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = r"D:\git\AINews"
VIDEO = os.path.join(ROOT, "data", "zelos", "zelos_promo_45s.mp4")
BGM = os.path.join(ROOT, "static", "music", "g小调的巴赫.mp3")
OUT = os.path.join(ROOT, "data", "zelos", "zelos_promo_45s_bgm.mp4")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop", "九识无人车", "九识加盟宣传_纪年模板_45s.mp4")

# Speech stays dominant; BGM sits around -18 dB relative to full scale.
BGM_VOLUME = 0.14


def probe_duration(path: str) -> float:
    out = subprocess.run(
        [FFMPEG, "-i", path, "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    for line in out.stderr.splitlines():
        if "Duration:" in line:
            part = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = part.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
    raise RuntimeError("could not probe duration")


def main() -> None:
    dur = probe_duration(VIDEO)
    fade_out = max(0.0, dur - 2.5)
    fc = (
        f"[1:a]aloop=loop=-1:size=2e+09,volume={BGM_VOLUME},"
        f"atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.3f}:d=2.5[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
    )
    cmd = [
        FFMPEG,
        "-y",
        "-i",
        VIDEO,
        "-i",
        BGM,
        "-filter_complex",
        fc,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        OUT,
    ]
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "ignore")[-3000:])

    # Replace the main deliverable and refresh the desktop copy.
    final = os.path.join(ROOT, "data", "zelos", "zelos_promo_45s.mp4")
    os.replace(OUT, final)
    if os.path.isdir(os.path.dirname(DESKTOP)):
        import shutil

        shutil.copy2(final, DESKTOP)
    print("mixed:", final, os.path.getsize(final))


if __name__ == "__main__":
    main()
