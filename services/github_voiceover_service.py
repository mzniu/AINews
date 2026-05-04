"""
GitHub 成片第五步：TTS 配音 + SRT 字幕 + 与 BGM 混音 + 可选烧录字幕。
依赖：IndexTTS、pydub、ffmpeg（PATH）、moviepy。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

# pydub 不在此处导入：避免 uvicorn 子进程与终端 pip 使用不同 Python 时误报「未安装」。
# IndexTTS 使用其项目内置 Python 子进程运行，避免将 torch/checkpoints 绑定到 AINews 当前解释器。

_DEFAULT_INDEXTTS_PROJECT_DIR = Path(
    os.getenv(
        "INDEXTTS_PROJECT_DIR",
        r"D:\BaiduNetdiskDownload\MetaHuman-2\MetaHuman4_V2\MetaHuman4_V2\tts-2",
    )
)


# 字幕断点标点（优先级从高到低分档，同档内从窗口尾部向前找）
_PUNCT_STRONG = frozenset("。！？!?…")  # 句末
_PUNCT_MEDIUM = frozenset("；;：:")  # 分句
_PUNCT_WEAK = frozenset("，,、·")  # 逗号、顿号
_PUNCT_CLAUSE = frozenset("）)」】』")  # 右括号、闭引号等
_PUNCT_SPACE = frozenset(" \t")  # 空格（英文词间）

_PUNCT_TIERS = (_PUNCT_STRONG, _PUNCT_MEDIUM, _PUNCT_WEAK, _PUNCT_CLAUSE, _PUNCT_SPACE)

# 字幕条末尾可去掉的标点（展示与 SRT/ASS 一致）
_TRAILING_SUBTITLE_PUNCT = frozenset(
    "。！？!?….,，、;；:：．"
)


def _strip_trailing_subtitle_punctuation(text: str) -> str:
    """去掉一条字幕末尾的句读标点（不影响中间标点）。"""
    s = (text or "").rstrip()
    if not s:
        return s
    orig = s
    while s and s[-1] in _TRAILING_SUBTITLE_PUNCT:
        s = s[:-1].rstrip()
    return s if s else orig


def _snap_cut_end_to_word_boundary(text: str, start: int, end: int) -> int:
    """
    若 end 落在英文/数字单词中间，将切分点移到词边界（优先空格，否则词首）。
    start/end 为切片 [start:end) 的 end。
    """
    end = min(max(start + 1, end), len(text))
    if end >= len(text):
        return end
    a, b = text[end - 1], text[end]
    if not (a.isascii() and a.isalnum() and b.isascii() and b.isalnum()):
        return end
    window = text[start:end]
    sp = window.rfind(" ")
    min_keep = max(2, len(window) // 5)
    if sp >= min_keep:
        return start + sp + 1
    j = end - 1
    while j > start and text[j].isascii() and text[j].isalnum():
        j -= 1
    if j > start:
        return j + 1
    return end


def _find_punctuation_break(window: str, min_prefix: int) -> int:
    """
    在 window 内从右向左按优先级查找断点，返回断点之后的长度（1..len(window)）。
    优先在 min_prefix 之后断句；若无标点再放宽到整窗扫描。
    找不到合适标点时返回 -1（由调用方硬切）。
    """
    n = len(window)
    if n <= min_prefix:
        return n
    for tier in _PUNCT_TIERS:
        for j in range(n - 1, min_prefix - 1, -1):
            if window[j] in tier:
                return j + 1
    for tier in _PUNCT_TIERS:
        for j in range(min_prefix - 1, 0, -1):
            if window[j] in tier:
                return j + 1
    return -1


def _chunk_long_sentence_flexible(
    text: str,
    *,
    target: int,
    soft_min: int,
    soft_max: int,
    float_amt: int,
) -> List[str]:
    """
    将超长句切成多段：单段长度优先落在 [soft_min, soft_max]（约 target±float_amt），
    在窗口内优先按标点断句，必要时略超 soft_max 再找标点，最后才硬切。
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= soft_max:
        return [text]
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        rest = n - i
        if rest <= soft_max:
            tail = text[i:].strip()
            if tail:
                out.append(tail)
            break
        stretch = min(rest, soft_max + float_amt)
        window = text[i : i + stretch]
        min_rel = max(2, min(soft_min, max(2, len(window) // 4)))
        br = _find_punctuation_break(window, min_prefix=min_rel)
        if br < 0:
            w2 = text[i : i + min(rest, soft_max)]
            br = _find_punctuation_break(w2, min_prefix=max(2, min(soft_min, len(w2) // 3)))
        if br < 0:
            best = min(soft_max, rest)
        else:
            # 在 stretch 内找到的断点；允许略超 soft_max 以落在标点上
            best = min(br, soft_max + float_amt, rest)
        end_idx = i + best
        end_idx = _snap_cut_end_to_word_boundary(text, i, end_idx)
        best = end_idx - i
        piece = text[i : i + best].strip()
        if piece:
            out.append(piece)
        i += best
        while i < n and text[i].isspace():
            i += 1
    return out


def _merge_coarse_parts_for_length(
    parts: List[str],
    soft_min: int,
    soft_max: int,
    float_amt: int,
) -> List[str]:
    """合并过短的粗分句，避免大量个位数字的段；尽量不合并到超过 soft_max+float_amt。"""
    if not parts:
        return []
    merged: List[str] = []
    buf = ""
    cap = soft_max + float_amt
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not buf:
            buf = p
            continue
        if len(buf) < soft_min and len(buf) + len(p) <= cap:
            buf += p
        else:
            merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged


def _split_script_to_segments(
    script: str,
    max_chars_per_cue: int = 20,
    *,
    float_amt: int = 10,
) -> List[str]:
    """
    拆成 TTS / SRT 共用片段：以 max_chars_per_cue 为中心，单段长度约 [中心−10, 中心+10]，
    优先在句号、分号、逗号等标点处断开；先粗分句再合并过短段，再对仍过长的段细分。
    """
    s = (script or "").strip()
    if not s:
        return []
    target = max(8, min(40, int(max_chars_per_cue)))
    soft_min = max(8, target - float_amt)
    soft_max = target + float_amt

    # 粗分：句末、换行、分号
    parts = re.split(r"(?<=[。！？!?…])\s*|\s*\n\s*|(?<=[；;])\s*", s)
    sentences = [p.strip() for p in parts if p.strip()]
    if not sentences:
        sentences = [s]

    merged = _merge_coarse_parts_for_length(sentences, soft_min, soft_max, float_amt)

    chunks: List[str] = []
    for seg in merged:
        if len(seg) <= soft_max:
            chunks.append(seg)
        else:
            chunks.extend(
                _chunk_long_sentence_flexible(
                    seg,
                    target=target,
                    soft_min=soft_min,
                    soft_max=soft_max,
                    float_amt=float_amt,
                )
            )
    out = [_strip_trailing_subtitle_punctuation(c) for c in chunks]
    out = [c for c in out if c.strip()]
    return out


def _fmt_srt_time(sec: float) -> str:
    td = timedelta(seconds=float(sec))
    total = int(td.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(segments: List[Tuple[str, float, float]], path: Path) -> None:
    lines = []
    for i, (text, start, end) in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
        lines.append(text.replace("\r", "").strip())
        lines.append("")
    # 无 BOM：首行若变成「\ufeff1」会导致部分解析器不显示任何字幕
    path.write_text("\n".join(lines), encoding="utf-8")


def _escape_filter_path_for_ffmpeg(path: Path) -> str:
    """ffmpeg subtitles/ass 滤镜路径：正斜杠 + 盘符冒号转义。"""
    p = path.resolve().as_posix()
    return p.replace(":", r"\\:")


def _fmt_ass_time(sec: float) -> str:
    """ASS 时间 H:MM:SS.cc（百分之一秒）。"""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    frac = sec - (h * 3600 + m * 60 + s)
    cs = int(round(frac * 100)) % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_dialogue_text(text: str) -> str:
    """ASS Dialogue 正文转义。"""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}")
    return t.replace("\n", r"\N")


def _ass_fontsize_pixels(ui_fontsize: int, play_res_y: int) -> int:
    """
    页面「烧录字号」10–36 为相对档位；ASS 的 Fontsize 是画布上的像素高。
    若直接写 12，在 1080p 上约 12px，几乎看不见。
    按视频高度换算：以 360 行高为 1× 基准，UI=12 在 1080p → 约 36px。
    """
    ui = max(8, min(48, int(ui_fontsize)))
    h = max(1, int(play_res_y))
    px = int(round(ui * h / 360.0))
    return max(16, min(120, px))


# 烧录字幕：无描边；阴影约 70% 不透明。不使用 \\blur（会令整字发糊），仅用 shad 偏移 + 半透明阴影色
# &HAABBGGRR：AA=4D ≈ 30% 透明 → 约 70% 不透明黑
_ASS_BURN_SHADOW_PREFIX = r"{\bord0\shad3\4c&H4D000000}"


def _ass_horizontal_margins(play_res_x: int) -> Tuple[int, int]:
    """左右留白（像素），限制字幕宽度以便 libass 自动换行。
    相对原约 8.5%/侧，收窄边距使可用宽度约 +10%。
    """
    prx = max(1, int(play_res_x))
    usable_ratio_old = 1.0 - 2 * 0.085
    usable_ratio_new = min(0.96, usable_ratio_old * 1.10)
    side_frac = (1.0 - usable_ratio_new) / 2.0
    m = max(40, int(round(prx * side_frac)))
    return m, m


def _ass_chars_per_line(play_res_x: int, margin_l: int, margin_r: int, fs_px: int) -> int:
    """按画布宽度估算每行约多少字（中日文约等宽），用于插入 \\N 硬换行。"""
    usable = max(100, int(play_res_x) - margin_l - margin_r)
    # 单字宽约 0.88～1.0 倍字号，略保守多换行
    cw = max(8.0, float(fs_px) * 0.92)
    return max(10, int(usable / cw))


def _wrap_text_for_ass_lines(
    text: str,
    max_chars_per_line: int,
) -> str:
    """
    将长句用 ASS 的 \\N 折行：按词边界（英文整词、中日文按字）累加行宽，避免在英文单词中间截断。
    """
    t = (text or "").strip()
    if not t:
        return ""
    m = max(6, int(max_chars_per_line))

    def esc_line(s: str) -> str:
        return s.replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}")

    def token_display_width(tok: str) -> int:
        if re.fullmatch(r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*", tok):
            return len(tok)
        return len(tok)

    def wrap_one_para(para: str) -> str:
        para = para.strip()
        if not para:
            return ""
        tokens = re.findall(
            r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*|"
            r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]|"
            r"[^\S\n]|[^\w\s]|\n",
            para,
        )
        lines: List[str] = []
        cur = ""
        cur_w = 0

        for tok in tokens:
            if tok == "\n":
                if cur.strip():
                    lines.append(cur)
                cur, cur_w = "", 0
                continue
            tw = token_display_width(tok)
            is_latin_word = bool(
                re.fullmatch(r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*", tok)
            )
            if not cur:
                if is_latin_word and tw > m:
                    lines.append(tok)
                    continue
                cur, cur_w = tok, tw
                continue
            if cur_w + tw <= m:
                cur += tok
                cur_w += tw
                continue
            lines.append(cur)
            if is_latin_word and tw > m:
                lines.append(tok)
                cur, cur_w = "", 0
            else:
                cur, cur_w = tok, tw
        if cur.strip():
            lines.append(cur)
        return r"\N".join(esc_line(ln) for ln in lines)

    blocks: List[str] = []
    for para in re.split(r"\n+", t):
        w = wrap_one_para(para)
        if w:
            blocks.append(w)
    return r"\N".join(blocks)


def _write_ass_for_burn(
    segments: List[Tuple[str, float, float]],
    path: Path,
    *,
    fontname: str,
    fontsize: int,
    margin_v: int,
    play_res_x: int,
    play_res_y: int,
) -> None:
    """
    写入 ASS，由 libass 按样式渲染；避免 subtitles+force_style 在 -vf 里被逗号拆坏。
    """
    fn = (fontname or "Microsoft YaHei").strip() or "Microsoft YaHei"
    fn = fn.replace(",", " ")[:80]
    pry = max(16, int(play_res_y))
    prx = max(16, int(play_res_x))
    # 页面字号 → ASS 像素（与 PlayRes 一致）
    fs = _ass_fontsize_pixels(int(fontsize), pry)
    mv = max(0, int(margin_v))
    ml, mr = _ass_horizontal_margins(prx)
    cpl = _ass_chars_per_line(prx, ml, mr, fs)
    logger.info(
        f"ASS 烧录: UI字号={fontsize} → Fontsize={fs}px, PlayRes={prx}x{pry}, "
        f"边距 L/R={ml}/{mr}, 底MarginV={mv}, 约每行{cpl}字, 无描边+阴影(无blur,shad3,α≈70%)"
    )

    header = f"""[Script Info]
Title: voiceover
ScriptType: v4.00+
PlayResX: {prx}
PlayResY: {pry}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fn},{fs},&H00FFFFFF,&H00000000,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,0,0,2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines_out = [header]
    for text, start, end in segments:
        raw = text.replace("\r", "").strip()
        if not raw:
            continue
        t = _wrap_text_for_ass_lines(raw, cpl)
        if not t:
            continue
        body = _ASS_BURN_SHADOW_PREFIX + t
        lines_out.append(
            f"Dialogue: 0,{_fmt_ass_time(start)},{_fmt_ass_time(end)},Default,,0,0,0,,{body}\n"
        )
    path.write_text("".join(lines_out), encoding="utf-8")


def _ffmpeg_burn_subtitles(
    temp_mp4: Path,
    ass_path: Path,
    srt_fallback_path: Path,
    final_mp4: Path,
    *,
    fontsdir: Optional[Path] = None,
) -> bool:
    """
    优先用 ASS + ass 滤镜烧录（样式在文件内，不经过 filtergraph 的逗号拆分）。
    失败再尝试仅 charenc 的 SRT subtitles。
    """
    ap = _escape_filter_path_for_ffmpeg(ass_path)
    sp = _escape_filter_path_for_ffmpeg(srt_fallback_path)
    ass_vf = f"ass={ap}"
    if fontsdir is not None and fontsdir.is_dir():
        fd = _escape_filter_path_for_ffmpeg(fontsdir.resolve())
        ass_vf = f"ass={ap}:fontsdir={fd}"
    attempts = [
        # 1) ASS（主路径；fontsdir 供 libass 加载 static/fonts/subtitle 下自定义 TTF/OTF）
        ass_vf,
        # 2) SRT 仅 UTF-8，无 force_style（避免 filter 语法问题）
        f"subtitles={sp}:charenc=UTF-8",
    ]
    venc = [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
    ]
    for vf in attempts:
        try:
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(temp_mp4),
                    "-vf",
                    vf,
                    *venc,
                    "-c:a",
                    "copy",
                    str(final_mp4),
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )
            err = (r.stderr or "")[-2000:]
            if r.returncode == 0 and final_mp4.is_file() and final_mp4.stat().st_size > 1000:
                logger.info(f"烧录字幕成功: {vf[:160]}")
                if "Error" in err or "Invalid" in err:
                    logger.warning(f"ffmpeg stderr 片段: {err[-600:]}")
                return True
            logger.warning(
                f"烧录字幕尝试失败 (code={r.returncode}): vf={vf}\n{err}"
            )
        except Exception as e:
            logger.warning(f"烧录字幕异常: {e}")
    return False


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stderr=subprocess.STDOUT,
    )
    return float(out.decode().strip())


def _ffprobe_video_height(path: Path) -> int:
    """首路视频流高度，用于字幕 MarginV（距底边为画面高的一定比例）。"""
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=height",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.STDOUT,
        )
        return max(1, int(float(out.decode().strip())))
    except Exception:
        return 1080


def _ffprobe_video_width(path: Path) -> int:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.STDOUT,
        )
        return max(1, int(float(out.decode().strip())))
    except Exception:
        return 1920


def _ffprobe_video_size(path: Path) -> Tuple[int, int]:
    return (_ffprobe_video_width(path), _ffprobe_video_height(path))


def _resolve_voice_clone_audio(voice_clone_audio_path: Optional[str]) -> Path:
    candidates: List[Path] = []
    if voice_clone_audio_path:
        candidates.append(Path(voice_clone_audio_path.strip().lstrip("/")))
    env_prompt = os.getenv("INDEXTTS_PROMPT_AUDIO")
    if env_prompt:
        candidates.append(Path(env_prompt))
    candidates.extend(
        [
            _DEFAULT_INDEXTTS_PROJECT_DIR / "tests" / "sample_prompt.wav",
            _DEFAULT_INDEXTTS_PROJECT_DIR / "examples" / "voice_01.wav",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "未找到 IndexTTS 参考音频。请上传声音克隆音频，或设置 INDEXTTS_PROMPT_AUDIO。"
    )


def _build_indextts_env(project_dir: Path) -> dict:
    env = os.environ.copy()
    py_dir = project_dir / "py312"
    path_parts = [
        py_dir,
        py_dir / "Scripts",
        py_dir / "ffmpeg" / "bin",
        py_dir / "Lib" / "site-packages" / "torch" / "lib",
        py_dir / "Library" / "bin",
    ]
    env["PYTHONHOME"] = ""
    env["PYTHONPATH"] = ""
    env["GRADIO_TEMP_DIR"] = str(project_dir / "tmp")
    env["HF_ENDPOINT"] = env.get("HF_ENDPOINT", "https://hf-mirror.com")
    env["HF_HOME"] = str(project_dir / "checkpoints")
    env["TRANSFORMERS_CACHE"] = str(project_dir / "tf_download")
    env["XFORMERS_FORCE_DISABLE_TRITON"] = "1"
    env["DS_BUILD_AIO"] = "0"
    env["DS_BUILD_SPARSE_ATTN"] = "0"
    env["PATH"] = os.pathsep.join(str(p) for p in path_parts) + os.pathsep + env.get("PATH", "")
    return env


def _synthesize_indextts_segments_blocking(
    segments: List[str],
    work_dir: Path,
    *,
    voice_clone_audio_path: Optional[str] = None,
) -> List[Path]:
    project_dir = Path(os.getenv("INDEXTTS_PROJECT_DIR", str(_DEFAULT_INDEXTTS_PROJECT_DIR))).resolve()
    python_exe = project_dir / "py312" / "python.exe"
    if not python_exe.is_file():
        raise FileNotFoundError(f"IndexTTS 内置 Python 不存在: {python_exe}")
    if not (project_dir / "checkpoints" / "config.yaml").is_file():
        raise FileNotFoundError(f"IndexTTS checkpoints/config.yaml 不存在: {project_dir}")

    prompt_audio = _resolve_voice_clone_audio(voice_clone_audio_path)
    segments_json = work_dir / "indextts_segments.json"
    wav_dir = work_dir / "indextts_wav"
    wav_dir.mkdir(parents=True, exist_ok=True)
    with segments_json.open("w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)

    worker = Path(__file__).with_name("indextts_worker.py").resolve()
    cmd = [
        str(python_exe),
        "-s",
        str(worker),
        "--project-dir",
        str(project_dir),
        "--segments-json",
        str(segments_json),
        "--output-dir",
        str(wav_dir),
        "--prompt-audio",
        str(prompt_audio),
        "--fast",
    ]
    if os.getenv("INDEXTTS_DEVICE"):
        cmd.extend(["--device", os.getenv("INDEXTTS_DEVICE", "")])
    if os.getenv("INDEXTTS_FP16", "1") not in {"0", "false", "False"}:
        cmd.append("--fp16")
    if os.getenv("INDEXTTS_USE_CUDA_KERNEL", "0") in {"1", "true", "True"}:
        cmd.append("--use-cuda-kernel")

    timeout = int(os.getenv("INDEXTTS_TIMEOUT_SECONDS", "1800"))
    logger.info(f"调用 IndexTTS 合成 {len(segments)} 段，参考音频: {prompt_audio}")
    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        env=_build_indextts_env(project_dir),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.error(f"IndexTTS stdout:\n{result.stdout[-4000:]}")
        logger.error(f"IndexTTS stderr:\n{result.stderr[-4000:]}")
        raise RuntimeError(f"IndexTTS 合成失败，退出码 {result.returncode}: {result.stderr[-1000:]}")

    paths = [wav_dir / f"seg_{i:03d}.wav" for i in range(len(segments))]
    missing = [str(p) for p in paths if not p.is_file() or p.stat().st_size <= 80]
    if missing:
        raise RuntimeError(f"IndexTTS 未生成有效音频: {missing[:3]}")
    return paths


async def _tts_save_segments(
    segments: List[str],
    work_dir: Path,
    *,
    voice_clone_audio_path: Optional[str] = None,
) -> List[Path]:
    return await asyncio.to_thread(
        _synthesize_indextts_segments_blocking,
        segments,
        work_dir,
        voice_clone_audio_path=voice_clone_audio_path,
    )


def _concat_audio_files_pydub(paths: List[Path], out_mp3: Path):
    from pydub import AudioSegment

    combined = AudioSegment.empty()
    for p in paths:
        combined += AudioSegment.from_file(str(p))
    combined.export(str(out_mp3), format="mp3")
    return combined


def _rate_to_speed(rate: str) -> float:
    m = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)%\s*", rate or "")
    if not m:
        return 1.0
    return max(0.5, min(2.0, 1.0 + float(m.group(1)) / 100.0))


async def render_voiceover_for_video(
    *,
    base_video_path: Path,
    script: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
    voice_clone_audio_path: Optional[str] = None,
    mix_bgm: bool = True,
    bgm_gain_db: float = -22.0,
    narration_gain_db: float = 0.0,
    burn_subtitles: bool = True,
    tts_rate: str = "+25%",
    subtitle_fontname: str = "Microsoft YaHei",
    subtitle_fontsize: int = 16,
    subtitle_margin_bottom_percent: float = 11.0,
    subtitle_max_chars: int = 20,
    output_dir: Optional[Path] = None,
) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    生成：旁白音轨、SRT、与 base 视频合成；可选烧录字幕。
    返回 (success, message, final_mp4_url_path, srt_url_path)，路径为以 / 开头的 URL 形式。

    必须为 async：在 FastAPI/uvicorn 已有事件循环时不能使用 asyncio.run()。
    """
    base_video_path = Path(base_video_path)
    if not base_video_path.is_file():
        return False, f"基底视频不存在: {base_video_path}", None, None

    script = (script or "").strip()
    if not script:
        return False, "口播稿为空", None, None

    import importlib
    import sys

    try:
        from pydub import AudioSegment
    except ImportError as e:
        err = str(e).lower()
        # Python 3.13+ 移除 stdlib audioop；pydub 需 audioop-lts（提供 audioop），否则会报 pyaudioop
        if "pyaudioop" in err or "audioop" in err:
            fix = (
                f"Python 3.13+ 需安装 audioop-lts："
                f"{sys.executable} -m pip install audioop-lts"
            )
        else:
            fix = f"{sys.executable} -m pip install pydub"
        return (
            False,
            f"无法导入 pydub：{e}。当前 Python：{sys.executable}。请执行：{fix}",
            None,
            None,
        )
    try:
        importlib.import_module("pydub")
    except ImportError as e:
        return False, f"无法导入 pydub：{e}。当前 Python：{sys.executable}", None, None

    segments = _split_script_to_segments(script, max_chars_per_cue=subtitle_max_chars)
    if not segments:
        return False, "口播稿无有效内容", None, None

    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_dir or (Path("data/videos") / f"voiceover_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)

    narr_mp3 = work / "narration.mp3"
    srt_path = out_dir / "voiceover.srt"

    try:
        await _tts_save_segments(segments, work, voice_clone_audio_path=voice_clone_audio_path)
        seg_paths = sorted(
            (work / "indextts_wav").glob("seg_*.wav"),
            key=lambda p: int(p.stem.rsplit("_", 1)[-1]),
        )
        narr_audio = _concat_audio_files_pydub(list(seg_paths), narr_mp3)
        speed = _rate_to_speed(tts_rate)
        if abs(speed - 1.0) > 0.01:
            narr_audio = narr_audio.speedup(playback_speed=speed, chunk_size=120, crossfade=20)
            narr_audio.export(str(narr_mp3), format="mp3")

        # 句级时间轴（累加每段时长）
        times: List[Tuple[str, float, float]] = []
        t0 = 0.0
        for i, seg in enumerate(segments):
            sp = seg_paths[i]
            dur = _ffprobe_duration(sp) / speed
            times.append((seg, t0, t0 + dur))
            t0 += dur
        _write_srt(times, srt_path)

        vdur = _ffprobe_duration(base_video_path)
        narr_audio = AudioSegment.from_file(str(narr_mp3), format="mp3")
        narr_audio = narr_audio.apply_gain(narration_gain_db)
        n_ms = len(narr_audio)
        v_ms = int(vdur * 1000)
        if n_ms < v_ms:
            narr_audio += AudioSegment.silent(duration=(v_ms - n_ms))
        elif n_ms > v_ms:
            narr_audio = narr_audio[:v_ms]

        # 混 BGM：从视频中提取
        mixed_audio = narr_audio
        tmp_bgm = work / "extracted_bgm.mp3"
        if mix_bgm:
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(base_video_path),
                        "-vn",
                        "-acodec",
                        "libmp3lame",
                        "-q:a",
                        "4",
                        str(tmp_bgm),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if tmp_bgm.is_file() and tmp_bgm.stat().st_size > 100:
                    bgm = AudioSegment.from_file(str(tmp_bgm), format="mp3")
                    bgm = bgm[: len(narr_audio)]
                    if len(bgm) < len(narr_audio):
                        bgm += AudioSegment.silent(duration=(len(narr_audio) - len(bgm)))
                    bgm = bgm.apply_gain(bgm_gain_db)
                    mixed_audio = narr_audio.overlay(bgm)
            except Exception as e:
                logger.warning(f"提取或混合 BGM 失败，仅使用旁白: {e}")
                mixed_audio = narr_audio

        mixed_wav = work / "mixed.wav"
        mixed_audio.export(str(mixed_wav), format="wav")

        temp_mp4 = work / "muxed.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(base_video_path),
                "-i",
                str(mixed_wav),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(temp_mp4),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        final_mp4 = out_dir / "final_with_voiceover.mp4"
        if burn_subtitles and srt_path.is_file():
            import shutil

            subs_for_ffmpeg = work / "subs_utf8.srt"
            shutil.copy2(srt_path, subs_for_ffmpeg)
            vw, vh = _ffprobe_video_size(temp_mp4)
            pct = float(subtitle_margin_bottom_percent)
            pct = max(8.0, min(45.0, pct))
            margin_v = max(8, int(round(vh * (pct / 100.0))))
            ass_path = work / "burn_subs.ass"
            _write_ass_for_burn(
                times,
                ass_path,
                fontname=str(subtitle_fontname or "Microsoft YaHei"),
                fontsize=int(subtitle_fontsize),
                margin_v=margin_v,
                play_res_x=vw,
                play_res_y=vh,
            )
            from utils.subtitle_fonts import resolved_fontsdir_for_ffmpeg

            ok = _ffmpeg_burn_subtitles(
                temp_mp4,
                ass_path,
                subs_for_ffmpeg,
                final_mp4,
                fontsdir=resolved_fontsdir_for_ffmpeg(),
            )
            if not ok:
                logger.warning("烧录字幕全部尝试失败，输出无硬字幕版本")
                shutil.copy2(temp_mp4, final_mp4)
        else:
            import shutil

            shutil.copy2(temp_mp4, final_mp4)

        rel = "/" + str(final_mp4.relative_to(Path("."))).replace("\\", "/")
        srel = "/" + str(srt_path.relative_to(Path("."))).replace("\\", "/")
        return True, "ok", rel, srel

    except Exception as e:
        logger.exception(f"配音合成失败: {e}")
        return False, str(e), None, None
