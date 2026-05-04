"""视频处理工具函数"""
import math
import os
import random
import re
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# 主标题文字块底边与副标题黄条之间的间距（在 17px 基础上再 +10px）
MAIN_SUBTITLE_GAP_PX = 27

# 主标题第一、二行白字字号（相对原先 66 小一号）
TITLE_MAIN_FONT_SIZE = 60

# 主标题 + 副标题自上方滑入的默认时长（秒；仅首个成片片段启用）
DEFAULT_TITLE_SLIDE_DURATION = 0.68

# 高图 scroll_up：匀速上滑（像素/秒），与图高无关。
# 总位移 = min(可滚动量 overflow, SCROLL_UP_PIXELS_PER_SEC × 上滑阶段秒数)；进度在阶段内线性 0→1。
SCROLL_UP_PIXELS_PER_SEC = 380.0


def _scroll_up_effective_distance(
    target_height: int,
    scroll_viewport_height: Optional[int],
    scroll_phase_sec: float,
) -> int:
    """
    上滑总像素：min(overflow, 匀速×上滑阶段秒数)。匀速 = SCROLL_UP_PIXELS_PER_SEC（与图高无关）。
    overflow：缩放后图高 − 可视槽高度（无槽信息时用图高估算）。
    """
    phase = max(0.05, float(scroll_phase_sec))
    if scroll_viewport_height is not None and scroll_viewport_height > 0:
        overflow = max(0, target_height - scroll_viewport_height)
    else:
        overflow = max(1, int(target_height * 0.28))
    if overflow <= 0:
        max_dist = max(1, int(target_height * 0.15))
    else:
        max_dist = overflow
    max_travel = SCROLL_UP_PIXELS_PER_SEC * phase
    raw = min(max_dist, max_travel)
    return max(1, int(round(raw)))


def compute_title_slide_offset_y(
    t: float,
    *,
    title_slide_delay: float = 0.0,
    title_slide_duration: float = DEFAULT_TITLE_SLIDE_DURATION,
    slide_px: int = 120,
) -> int:
    """
    返回加在 title_y 上的纵向偏移（≤0），使主标题与副标题作为整体自上方滑入。
    t < delay 时固定在起点（画面上方）；delay ≤ t < delay+duration 时缓出；之后为 0。
    """
    if title_slide_duration <= 0:
        return 0
    slide_px = max(0, int(slide_px))
    if slide_px == 0:
        return 0
    tt = t - title_slide_delay
    if tt < 0:
        return -slide_px
    if tt >= title_slide_duration:
        return 0
    progress = max(0.0, min(1.0, tt / title_slide_duration))
    ease = 1 - (1 - progress) ** 3
    return -int(round(slide_px * (1 - ease)))

# 摘要中匹配关键字时的强调色（高饱和金黄，相对白字更醒目）
DEFAULT_SUMMARY_HIGHLIGHT_COLOR = (255, 236, 48)
# 关键字描边，增强与白字/背景的分离度
SUMMARY_HIGHLIGHT_STROKE_FILL = (55, 28, 0)


def merge_summary_highlight_keywords(
    explicit: Optional[List[str]] = None,
    tags: Optional[str] = None,
) -> List[str]:
    """合并显式关键字与标签串（支持 #词 与空格分隔）。"""
    out: List[str] = []
    for e in explicit or []:
        s = (e or "").strip()
        if s:
            out.append(s)
    if tags:
        for part in tags.replace("，", " ").split():
            w = part.strip().lstrip("#").strip()
            if w:
                out.append(w)
    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _build_highlight_pattern(keywords: List[str]) -> Optional[str]:
    if not keywords:
        return None
    kws = sorted({k.strip() for k in keywords if k and k.strip()}, key=len, reverse=True)
    if not kws:
        return None
    return "|".join(re.escape(k) for k in kws)


def _split_line_highlight_segments(line: str, pattern: str) -> List[Tuple[str, bool]]:
    if not pattern or not line:
        return [(line, False)]
    segs: List[Tuple[str, bool]] = []
    last = 0
    for m in re.finditer(pattern, line):
        if m.start() > last:
            segs.append((line[last:m.start()], False))
        segs.append((m.group(), True))
        last = m.end()
    if last < len(line):
        segs.append((line[last:], False))
    return segs if segs else [(line, False)]


def _unpack_summary_info(summary_info):
    """兼容 3 元组与 4 元组 (font, lines, y, highlight_keywords)。"""
    if not summary_info:
        return None, None, None, []
    if len(summary_info) == 3:
        f, lines, y = summary_info
        return f, lines, y, []
    f, lines, y, kw = summary_info[0], summary_info[1], summary_info[2], summary_info[3]
    return f, lines, y, list(kw or [])


def _draw_text_line_shadow_segments(
    draw,
    x: float,
    y: float,
    segments: List[Tuple[str, bool]],
    font,
    base_color: Tuple[int, int, int],
    highlight_color: Tuple[int, int, int],
) -> None:
    """左对齐一行：分段着色（摘要用）。高亮段加粗描边与更亮填充。"""
    cx = x
    for text, is_hi in segments:
        if not text:
            continue
        fill = highlight_color if is_hi else base_color
        if is_hi:
            draw.text((cx + 4, y + 4), text, font=font, fill=(0, 0, 0))
            draw.text(
                (cx, y),
                text,
                font=font,
                fill=fill,
                stroke_width=2,
                stroke_fill=SUMMARY_HIGHLIGHT_STROKE_FILL,
            )
        else:
            draw.text((cx + 3, y + 3), text, font=font, fill=(0, 0, 0))
            draw.text((cx + 1, y + 1), text, font=font, fill=(10, 10, 30))
            draw.text((cx, y), text, font=font, fill=fill)
        if is_hi:
            bb = draw.textbbox((0, 0), text, font=font, stroke_width=2)
        else:
            bb = draw.textbbox((0, 0), text, font=font)
        cx += bb[2] - bb[0]


# 主标题字形预设：key -> 候选文件名（依次在 cwd 与 Windows/Fonts 下查找）
_TITLE_FONT_CANDIDATES: Dict[str, List[str]] = {
    "msyhbd": ["msyhbd.ttc"],
    "msyh": ["msyh.ttc"],
    "simhei": ["simhei.ttf", "simhei.ttc"],
    "simsun": ["simsun.ttc", "simsun.ttf"],
    "kaiti": ["simkai.ttf", "STKAITI.TTF", "stkaiti.ttf"],
}


def title_font_presets_for_api() -> List[Dict[str, str]]:
    """供 GET /api/list-title-fonts 返回。"""
    return [
        {"key": "msyhbd", "label": "微软雅黑 粗体"},
        {"key": "msyh", "label": "微软雅黑"},
        {"key": "simhei", "label": "黑体"},
        {"key": "simsun", "label": "宋体"},
        {"key": "kaiti", "label": "楷体"},
    ]


def _find_font_path(candidates: List[str]) -> Optional[str]:
    """在 cwd、static/fonts、Windows Fonts 中查找首个存在的字体文件。"""
    windir = os.environ.get("WINDIR", "C:/Windows")
    font_dirs = [
        Path("."),
        Path("static/fonts"),
        Path(windir) / "Fonts",
    ]
    for name in candidates:
        for base in font_dirs:
            p = base / name
            if p.is_file():
                return str(p.resolve())
    return None


def _load_title_font_truetype(title_font_key: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    key = (title_font_key or "msyhbd").strip().lower()
    names = _TITLE_FONT_CANDIDATES.get(key, _TITLE_FONT_CANDIDATES["msyhbd"])
    path = _find_font_path(names)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    for fb in ("msyhbd.ttc", "simhei.ttf"):
        p2 = _find_font_path([fb])
        if p2:
            try:
                return ImageFont.truetype(p2, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _load_fonts(title_font_key: Optional[str] = None):
    """加载字体，返回 (title_font, subtitle_font, summary_font)；主标题字形由 title_font_key 选择。"""
    title_font = _load_title_font_truetype(title_font_key, TITLE_MAIN_FONT_SIZE)
    try:
        p58 = _find_font_path(["msyhbd.ttc"]) or _find_font_path(["simhei.ttf"])
        p40 = _find_font_path(["msyh.ttc"]) or _find_font_path(["simhei.ttf"])
        if p58 and p40:
            subtitle_font = ImageFont.truetype(p58, 58)
            summary_font = ImageFont.truetype(p40, 40)
            return title_font, subtitle_font, summary_font
    except OSError:
        pass
    try:
        p = _find_font_path(["simhei.ttf"])
        if p:
            return (
                title_font,
                ImageFont.truetype(p, 58),
                ImageFont.truetype(p, 40),
            )
    except OSError:
        pass
    df = ImageFont.load_default()
    return title_font, df, df


def _wrap_text(text, font, max_width, draw_obj):
    """词感知自动换行（不截断英文单词）"""
    tokens = re.findall(
        r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*|[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]|[^\S\n]|[^\w\s]|\n",
        text
    )
    lines, current_line = [], ""
    for token in tokens:
        if token == '\n':
            lines.append(current_line)
            current_line = ""
            continue
        test_line = current_line + token
        bbox = draw_obj.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line.strip():
                lines.append(current_line)
                current_line = token.lstrip() if token.isspace() else token
            else:
                for char in token:
                    test_char = current_line + char
                    bbox = draw_obj.textbbox((0, 0), test_char, font=font)
                    if bbox[2] - bbox[0] <= max_width:
                        current_line = test_char
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = char
    if current_line:
        lines.append(current_line)
    return lines


def _break_summary_by_punctuation(text: str) -> str:
    """仅在句末标点后插入换行（再经 _wrap_text 按宽度折行）。句末：。！？及英文 . ! ?（避免小数点）。"""
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"([。！？])\s*", r"\1\n", s)
    # 英文句末：. ! ? 不在数字后
    s = re.sub(r"(?<![0-9])([.!?])(?=\s|$|\n)", r"\1\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def _render_frame_animated(bg_template, user_img_resized, paste_x, final_paste_y,
                          target_width, target_height, img_width, img_height,
                          title_info, summary_info, t, entrance_duration=0.6,
                          hold_with_text_start=0.8, anim_type='zoom_in',
                          zoom_effect=False, zoom_start_scale=1.0, 
                          zoom_end_scale=1.15, clip_duration=None,
                          summary_scroll=False,
                          summary_scroll_mode: str = "block",
                          summary_segments=None,
                          title_slide_duration=DEFAULT_TITLE_SLIDE_DURATION,
                          title_slide_px=None,
                          title_slide_delay=None,
                          title_slide_entrance: bool = True,
                          scroll_viewport_height: Optional[int] = None,
                          clip_fps: float = 24.0):
    """
    渲染动画的某一帧（时间 t 秒）。
    anim_type: 'zoom_in'(动感放大), 'zoom_out'(动感缩小), 'unfold'(展开),
              'scroll_up'(向上滚动), 'slide_left'(左滑入), 'slide_right'(右滑入),
              'fade_in'(淡入), 'drop_bounce'(垂落弹跳)
    zoom_effect: 是否启用持续放大效果
    zoom_start_scale: 起始缩放比例
    zoom_end_scale: 结束缩放比例
    clip_duration: 片段总时长（用于计算放大进度）
    summary_scroll: 是否启用摘要滚动显示
    summary_scroll_mode: "block" 整块上滑；"line_uniform" 方案 A 逐行均分时段上滑
    summary_segments: 摘要分段信息 [(text1, y1), (text2, y2), (text3, y3)]
    title_slide_duration: 主标题+副标题自上方滑入时长（秒）
    title_slide_px: 滑入起点相对终点的上移像素；None 则按画布高度估算
    title_slide_delay: 滑入开始时刻（秒）；None 表示在图片入场结束（entrance_duration）后开始
    title_slide_entrance: False 时标题/副标题不播放滑入（用于非首段成片）
    返回 numpy array (H, W, 3) uint8
    """
    bg = bg_template.copy().convert('RGB')

    # --- 阶段 1: 小图入场动画 ---
    if t < entrance_duration:
        progress = t / entrance_duration
        # 缓出曲线
        ease = 1 - (1 - progress) ** 3

        if anim_type == 'zoom_in':
            # 动感放大：从小到大 + 轻微弹跳
            scale = 0.3 + 0.7 * ease
            bounce = 1 + 0.08 * math.sin(math.pi * progress) * (1 - progress)
            scale *= bounce
            sw = int(target_width * scale)
            sh = int(target_height * scale)
            if sw > 0 and sh > 0:
                scaled = user_img_resized.resize((sw, sh), Image.Resampling.LANCZOS)
                sx = paste_x + (target_width - sw) // 2
                sy = final_paste_y + (target_height - sh) // 2
                _safe_paste(bg, scaled, sx, sy)

        elif anim_type == 'zoom_out':
            # 动感缩小：从大到正常 + 轻微弹跳
            scale = 1.6 - 0.6 * ease
            bounce = 1 + 0.06 * math.sin(math.pi * progress) * (1 - progress)
            scale *= bounce
            sw = int(target_width * scale)
            sh = int(target_height * scale)
            if sw > 0 and sh > 0:
                scaled = user_img_resized.resize((sw, sh), Image.Resampling.LANCZOS)
                sx = paste_x + (target_width - sw) // 2
                sy = final_paste_y + (target_height - sh) // 2
                _safe_paste(bg, scaled, sx, sy)

        elif anim_type == 'unfold':
            # 展开：从中间横向展开
            reveal_w = max(1, int(target_width * ease))
            reveal_h = max(1, int(target_height * (0.4 + 0.6 * ease)))
            # 从中心裁剪出可见区域
            cx = target_width // 2
            cy_img = target_height // 2
            left = cx - reveal_w // 2
            top = cy_img - reveal_h // 2
            right = left + reveal_w
            bottom = top + reveal_h
            cropped = user_img_resized.crop((max(0, left), max(0, top),
                                             min(target_width, right), min(target_height, bottom)))
            px = paste_x + (target_width - cropped.width) // 2
            py = final_paste_y + (target_height - cropped.height) // 2
            _safe_paste(bg, cropped, px, py)

        elif anim_type == 'scroll_up':
            # 入场：从下方滑入（持续上滑在 t >= entrance_duration 分支）
            start_y = img_height + 50
            cur_y = int(start_y + (final_paste_y - start_y) * ease)
            _safe_paste(bg, user_img_resized, paste_x, cur_y)

        elif anim_type == 'slide_left':
            # 左滑入：从右侧滑入
            start_x = img_width + 50
            cur_x = int(start_x + (paste_x - start_x) * ease)
            _safe_paste(bg, user_img_resized, cur_x, final_paste_y)

        elif anim_type == 'slide_right':
            # 右滑入：从左侧滑入
            start_x = -target_width - 50
            cur_x = int(start_x + (paste_x - start_x) * ease)
            _safe_paste(bg, user_img_resized, cur_x, final_paste_y)

        elif anim_type == 'fade_in':
            # 淡入：透明度从 0 到 1
            alpha = ease
            temp = bg.copy()
            _safe_paste(temp, user_img_resized, paste_x, final_paste_y)
            bg = Image.blend(bg, temp, alpha)

        elif anim_type == 'drop_bounce':
            # 垂落弹跳：从上方落下 + 阻尼弹跳
            bounce_val = 1 - math.exp(-5 * progress) * math.cos(3 * math.pi * progress)
            bounce_val = max(0.0, min(bounce_val, 1.3))
            start_y = -target_height - 50
            cur_y = int(start_y + (final_paste_y - start_y) * bounce_val)
            _safe_paste(bg, user_img_resized, paste_x, cur_y)

    else:
        # 小图已落定：scroll_up 持续上滑；或持续放大；否则静态粘贴
        if anim_type == 'scroll_up':
            if clip_duration and clip_duration > entrance_duration:
                scroll_phase = clip_duration - entrance_duration
                scroll_progress = (t - entrance_duration) / scroll_phase
            elif clip_duration and clip_duration > 0:
                scroll_phase = max(clip_duration, 1e-6)
                scroll_progress = t / scroll_phase
            else:
                scroll_progress = 1.0
            scroll_progress = max(0.0, min(1.0, scroll_progress))
            phase_for_dist = (
                (clip_duration - entrance_duration)
                if clip_duration and clip_duration > entrance_duration
                else (clip_duration if clip_duration else 1.0)
            )
            scroll_dist = _scroll_up_effective_distance(
                target_height,
                scroll_viewport_height,
                phase_for_dist,
            )
            # 用浮点偏移再取整，减少小 scroll_dist 时多帧同一 y 的卡顿感
            offset_y = float(scroll_dist) * float(scroll_progress)
            cur_y = int(round(float(final_paste_y) - offset_y))
            _safe_paste(bg, user_img_resized, paste_x, cur_y)
        elif zoom_effect and clip_duration and clip_duration > entrance_duration:
            # 计算放大阶段的进度（从 entrance_duration 到 clip_duration）
            zoom_progress = (t - entrance_duration) / (clip_duration - entrance_duration)
            zoom_progress = max(0.0, min(1.0, zoom_progress))  # 限制在 [0, 1]
            
            # 使用缓动曲线让放大更自然（先快后慢）
            zoom_ease = 1 - (1 - zoom_progress) ** 2
            
            # 计算当前缩放比例
            current_scale = zoom_start_scale + (zoom_end_scale - zoom_start_scale) * zoom_ease
            
            # 计算缩放后的尺寸
            scaled_w = int(target_width * current_scale)
            scaled_h = int(target_height * current_scale)
            
            if scaled_w > 0 and scaled_h > 0:
                # 缩放图片
                scaled_img = user_img_resized.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                
                # 计算新的粘贴位置（保持中心点不变）
                new_x = paste_x + (target_width - scaled_w) // 2
                new_y = final_paste_y + (target_height - scaled_h) // 2
                
                # 安全粘贴
                _safe_paste(bg, scaled_img, new_x, new_y)
        else:
            # 没有放大效果，直接粘贴原图
            if user_img_resized.mode == 'RGBA':
                bg.paste(user_img_resized, (paste_x, final_paste_y), user_img_resized)
            else:
                bg.paste(user_img_resized, (paste_x, final_paste_y))

    # --- 标题（必选若有 title_info）；摘要仅在 summary_info 非空时绘制 ---
    if title_info:
        t_font, st_font, main_lines, sub_lines, title_y, main_h, margin, text_width = title_info

        _slide_delay = (
            entrance_duration if title_slide_delay is None else float(title_slide_delay)
        )
        _slide_px = (
            title_slide_px
            if title_slide_px is not None
            else max(80, min(200, int(img_height * 0.07)))
        )
        if title_slide_entrance:
            title_y_off = compute_title_slide_offset_y(
                t,
                title_slide_delay=_slide_delay,
                title_slide_duration=title_slide_duration,
                slide_px=_slide_px,
            )
        else:
            title_y_off = 0
        title_y_draw = title_y + title_y_off

        # 主标题：白色 + 蓝色光晕（背景条自画面顶部铺满至主标题区下缘）
        bg, _ = _draw_text_overlay(
            bg, main_lines, t_font, title_y_draw, img_width, margin, text_width,
            text_color=(255, 255, 255), glow_color=(102, 126, 234), line_spacing=18,
            background_top_y=0,
        )
        # 副标题：黄底黑字，紧跟主标题下方（与主标题同位移，整体自上方滑入）
        if sub_lines:
            sub_y = title_y_draw + main_h + MAIN_SUBTITLE_GAP_PX
            bg, _ = _draw_subtitle_yellow_bar(
                bg, sub_lines, st_font, sub_y, img_width, margin, text_width,
                line_spacing=14,
            )

        if not summary_info:
            return np.array(bg)

        summary_font, summary_lines, summary_y, summary_hi_kw = _unpack_summary_info(
            summary_info
        )
        if not summary_lines:
            return np.array(bg)
        
        # 摘要滚动显示逻辑
        if summary_scroll and summary_segments and len(summary_segments) == 3:
            # 使用分段滚动（旧逻辑）
            scroll_start_time = entrance_duration + hold_with_text_start  # 约 1.4s
            segment_duration = 0.8  # 每段间隔 0.8 秒
            
            for i, (segment_text, seg_y) in enumerate(summary_segments):
                # 计算该段的显示进度
                seg_start_time = scroll_start_time + i * segment_duration
                seg_progress = (t - seg_start_time) / segment_duration
                
                if t >= seg_start_time:
                    # 使用缓入曲线（从慢到快）
                    ease = seg_progress ** 2 if seg_progress < 1.0 else 1.0
                    
                    # 计算透明度（从 0 到 1）
                    alpha = min(1.0, ease)
                    
                    # 计算滑动偏移（从下方 50px 滑入）
                    slide_offset = int(50 * (1 - alpha))
                    current_y = seg_y + slide_offset
                    
                    # 绘制这段摘要
                    temp_bg, _ = _draw_text_overlay(
                        bg, [segment_text], summary_font, current_y,
                        img_width, margin, text_width,
                        text_color=(255, 255, 255), line_spacing=12, align="left",
                        highlight_keywords=summary_hi_kw or None,
                        background_bottom_y=img_height,
                    )
                    
                    # 应用透明度
                    if alpha < 1.0:
                        overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                        temp_bg_rgba = temp_bg.convert('RGBA')
                        for x in range(bg.width):
                            for y in range(bg.height):
                                orig_pixel = bg.getpixel((x, y))
                                new_pixel = temp_bg_rgba.getpixel((x, y))
                                # 混合颜色
                                r = int(orig_pixel[0] * (1 - alpha) + new_pixel[0] * alpha)
                                g = int(orig_pixel[1] * (1 - alpha) + new_pixel[1] * alpha)
                                b = int(orig_pixel[2] * (1 - alpha) + new_pixel[2] * alpha)
                                overlay.putpixel((x, y), (r, g, b, 255))
                        bg = overlay.convert('RGB')
                    else:
                        bg = temp_bg
        elif (
            summary_scroll
            and summary_scroll_mode == "line_uniform"
            and summary_info
        ):
            bg = _draw_summary_line_uniform_scheme_a(
                bg,
                summary_font=summary_font,
                summary_lines=summary_lines,
                summary_y=summary_y,
                summary_hi_kw=summary_hi_kw,
                img_width=img_width,
                margin=margin,
                text_width=text_width,
                t=t,
                entrance_duration=entrance_duration,
                clip_duration=clip_duration,
            )
        elif summary_scroll and summary_info:
            # 首张图片段内：摘要自下而上滚入，在 clip_duration 内完成；左对齐
            scroll_duration = (
                clip_duration if clip_duration and clip_duration > 0 else 1.2
            )
            scroll_progress = min(1.0, max(0.0, t / scroll_duration))
            ease = 1 - (1 - scroll_progress) ** 3
            slide_max = 100
            slide_offset = int(slide_max * (1 - ease))
            # 自下方移入：起始 y 更大，结束时落在 summary_y
            current_y = summary_y + slide_offset
            bg, _ = _draw_text_overlay(
                bg, summary_lines, summary_font, current_y,
                img_width, margin, text_width,
                text_color=(255, 255, 255), line_spacing=12, align="left",
                highlight_keywords=summary_hi_kw or None,
                background_bottom_y=img_height,
            )
        else:
            # 后续片段等：摘要静止、左对齐
            bg, _ = _draw_text_overlay(
                bg, summary_lines, summary_font, summary_y, img_width, margin, text_width,
                text_color=(255, 255, 255), line_spacing=12, align="left",
                highlight_keywords=summary_hi_kw or None,
                background_bottom_y=img_height,
            )

    return np.array(bg)


def _apply_video_effect(frame_array, t, effect, width, height, clip_duration, seed=0):
    """
    在帧上叠加视觉特效。
    effect: 'none', 'gold_sparkle'(金粉闪闪), 'snowfall'(雪花飘落),
            'bokeh'(光斑), 'firefly'(萤火虫), 'bubble'(气泡)
    frame_array: numpy (H, W, 3) uint8
    返回 numpy (H, W, 3) uint8
    """
    if effect == 'none' or not effect:
        return frame_array

    img = Image.fromarray(frame_array).convert('RGBA')
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    rng = random.Random(seed)
    # 预生成粒子位置（基于seed固定）
    num_particles = 60
    particles = []
    for _ in range(num_particles):
        particles.append({
            'x': rng.uniform(0, width),
            'y': rng.uniform(0, height),
            'speed': rng.uniform(0.3, 1.0),
            'size': rng.uniform(2, 8),
            'phase': rng.uniform(0, math.pi * 2),
            'drift': rng.uniform(-30, 30),
        })

    if effect == 'gold_sparkle':
        # 金粉闪闪：金色小光点随机闪烁
        for p in particles:
            # 闪烁：alpha随时间正弦变化
            flicker = 0.5 + 0.5 * math.sin(t * 8 + p['phase'])
            alpha = int(200 * flicker)
            if alpha < 30:
                continue
            # 缓慢下落 + 横向飘
            px = int((p['x'] + p['drift'] * math.sin(t * 1.5 + p['phase'])) % width)
            py = int((p['y'] + t * p['speed'] * 80) % height)
            sz = max(1, int(p['size'] * (0.6 + 0.4 * flicker)))
            # 金色系
            r = rng.randint(220, 255)
            g = rng.randint(180, 220)
            b = rng.randint(50, 100)
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(r, g, b, alpha))
            # 十字星芒
            if sz > 3 and flicker > 0.7:
                arm = sz * 2
                for dx, dy in [(arm, 0), (-arm, 0), (0, arm), (0, -arm)]:
                    draw.line([px, py, px + dx, py + dy], fill=(255, 230, 120, int(alpha * 0.6)), width=1)

    elif effect == 'snowfall':
        # 雪花飘落
        for p in particles:
            py = int((p['y'] + t * p['speed'] * 60) % height)
            px = int((p['x'] + 20 * math.sin(t * 2 + p['phase'])) % width)
            sz = max(1, int(p['size']))
            alpha = int(180 + 60 * math.sin(t * 3 + p['phase']))
            alpha = max(0, min(255, alpha))
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(255, 255, 255, alpha))

    elif effect == 'bokeh':
        # 柔和光斑
        num_bokeh = 20
        for i, p in enumerate(particles[:num_bokeh]):
            px = int((p['x'] + 15 * math.sin(t * 0.8 + p['phase'])) % width)
            py = int((p['y'] + 10 * math.cos(t * 0.6 + p['phase'])) % height)
            sz = int(p['size'] * 4 + 8)
            flicker = 0.4 + 0.6 * math.sin(t * 2 + p['phase'])
            alpha = int(50 * flicker)
            colors = [(255, 200, 100), (200, 150, 255), (150, 220, 255), (255, 180, 200)]
            c = colors[i % len(colors)]
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(c[0], c[1], c[2], alpha))

    elif effect == 'firefly':
        # 萤火虫：暖黄色小光点缓慢游动
        num_ff = 25
        for p in particles[:num_ff]:
            px = int((p['x'] + 40 * math.sin(t * 0.7 + p['phase'])) % width)
            py = int((p['y'] + 30 * math.cos(t * 0.5 + p['phase'])) % height)
            glow = 0.5 + 0.5 * math.sin(t * 4 + p['phase'])
            alpha = int(180 * glow)
            sz = max(1, int(p['size'] * 0.8))
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(255, 240, 80, alpha))
            # 光晕
            hsz = sz * 3
            draw.ellipse([px - hsz, py - hsz, px + hsz, py + hsz], fill=(255, 240, 80, int(alpha * 0.15)))

    elif effect == 'bubble':
        # 气泡：半透明圆，缓慢上升
        num_bub = 20
        for p in particles[:num_bub]:
            py = int((p['y'] - t * p['speed'] * 50) % height)
            px = int((p['x'] + 15 * math.sin(t * 1.2 + p['phase'])) % width)
            sz = int(p['size'] * 3 + 6)
            alpha = int(60 + 30 * math.sin(t * 2 + p['phase']))
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(200, 230, 255, alpha))
            # 高光
            hx = px - sz // 3
            hy = py - sz // 3
            hsz = max(1, sz // 4)
            draw.ellipse([hx - hsz, hy - hsz, hx + hsz, hy + hsz], fill=(255, 255, 255, int(alpha * 1.5)))

    # 合成
    img = Image.alpha_composite(img, overlay)
    return np.array(img.convert('RGB'))


def _apply_summary_gradient_background(
    bg: Image.Image,
    start_y: int,
    total_h: int,
    img_width: int,
    background_bottom_y: Optional[int] = None,
) -> Image.Image:
    """与 _draw_text_overlay 摘要区相同的半透明条背景。
    background_bottom_y: 若指定（如画布高度），背景下缘铺到该 y（不含），用于摘要区贴视频下沿。"""
    bg_y = start_y - 25
    span_end = bg_y + total_h + 40
    if background_bottom_y is not None:
        span_end = max(span_end, int(background_bottom_y))
    _, ih = bg.size
    span_end = min(span_end, ih)
    bg_h = max(1, span_end - bg_y)
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(bg_h):
        p = i / bg_h if bg_h else 0
        alpha = int(220 * (min(p, 1 - p) / 0.1 if min(p, 1 - p) < 0.1 else 1))
        od.rectangle([(0, bg_y + i), (img_width, bg_y + i + 1)], fill=(20, 20, 40, alpha))
    return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")


def _draw_one_summary_line_left(
    bg: Image.Image,
    line: str,
    font,
    cy: int,
    img_width: int,
    margin: int,
    text_width: int,
    highlight_keywords: Optional[List[str]],
) -> None:
    """单行摘要：左对齐，与 _draw_text_overlay 单行逻辑一致（无整块背景）。"""
    draw = ImageDraw.Draw(bg)
    hl_kw = [k.strip() for k in (highlight_keywords or []) if k and k.strip()]
    hl_pattern = _build_highlight_pattern(hl_kw) if hl_kw else None
    bbox = draw.textbbox((0, 0), line, font=font)
    use_hl = bool(hl_pattern)
    if use_hl:
        segs = _split_line_highlight_segments(line, hl_pattern)
        total_w = 0.0
        for seg, _ in segs:
            if not seg:
                continue
            bb = draw.textbbox((0, 0), seg, font=font)
            total_w += bb[2] - bb[0]
        lw = total_w
    else:
        segs = None
        lw = bbox[2] - bbox[0]
    x = margin
    if use_hl and segs:
        _draw_text_line_shadow_segments(
            draw,
            float(x),
            float(cy),
            segs,
            font,
            (255, 255, 255),
            DEFAULT_SUMMARY_HIGHLIGHT_COLOR,
        )
    else:
        draw.text((x + 3, cy + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x + 1, cy + 1), line, font=font, fill=(10, 10, 30))
        draw.text((x, cy), line, font=font, fill=(255, 255, 255))


def _draw_summary_line_uniform_scheme_a(
    bg: Image.Image,
    *,
    summary_font,
    summary_lines: List[str],
    summary_y: int,
    summary_hi_kw: Optional[List[str]],
    img_width: int,
    margin: int,
    text_width: int,
    t: float,
    entrance_duration: float,
    clip_duration: Optional[float],
    line_spacing: int = 12,
    slide_max_px: int = 100,
) -> Image.Image:
    """
    摘要方案 A：将 [entrance_duration, clip_duration] 均分为 n 段，
    第 i 行在对应 slot 内自下而上滑入（缓动与整块摘要一致）。
    """
    if not summary_lines:
        return bg
    draw = ImageDraw.Draw(bg)
    line_tops: List[float] = []
    cy = float(summary_y)
    total_h = 0
    for line in summary_lines:
        bbox = draw.textbbox((0, 0), line, font=summary_font)
        line_h = bbox[3] - bbox[1]
        line_tops.append(cy)
        total_h += line_h + line_spacing
        cy += line_h + line_spacing

    scroll_start = float(entrance_duration)
    cd = float(clip_duration) if clip_duration and clip_duration > 0 else 1.2
    T = max(1e-3, cd - scroll_start)
    n = len(summary_lines)
    slot = T / n

    if t < scroll_start:
        return bg

    bg = _apply_summary_gradient_background(
        bg, summary_y, total_h, img_width,
        background_bottom_y=bg.size[1],
    )

    for i, line in enumerate(summary_lines):
        t0 = scroll_start + i * slot
        t1 = scroll_start + (i + 1) * slot
        if t < t0:
            continue
        if t >= t1:
            offset = 0
        else:
            local_p = (t - t0) / slot
            local_p = max(0.0, min(1.0, local_p))
            ease = 1 - (1 - local_p) ** 3
            offset = int(slide_max_px * (1 - ease))
        y = int(line_tops[i]) + offset
        _draw_one_summary_line_left(
            bg,
            line,
            summary_font,
            y,
            img_width,
            margin,
            text_width,
            summary_hi_kw,
        )
    return bg


def _safe_paste(bg, img, x, y):
    """安全粘贴：处理图片部分在画面外的情况"""
    bg_w, bg_h = bg.size
    iw, ih = img.size

    # 计算源图和目标的裁剪区域
    src_x1 = max(0, -x)
    src_y1 = max(0, -y)
    src_x2 = min(iw, bg_w - x)
    src_y2 = min(ih, bg_h - y)

    if src_x2 <= src_x1 or src_y2 <= src_y1:
        return  # 完全在画面外

    dst_x = max(0, x)
    dst_y = max(0, y)

    cropped = img.crop((src_x1, src_y1, src_x2, src_y2))
    if cropped.mode == 'RGBA':
        bg.paste(cropped, (dst_x, dst_y), cropped)
    else:
        bg.paste(cropped, (dst_x, dst_y))


def _draw_text_overlay(bg, lines, font, start_y, img_width, margin, text_width,
                      text_color=(255, 255, 255), glow_color=None, line_spacing=12,
                      align="center",
                      highlight_keywords: Optional[List[str]] = None,
                      highlight_color: Tuple[int, int, int] = DEFAULT_SUMMARY_HIGHLIGHT_COLOR,
                      background_top_y: Optional[int] = None,
                      background_bottom_y: Optional[int] = None):
    """在图片上绘制带半透明背景的文字块，返回 (result_image, block_height)。
    align: 'center' | 'left'（摘要建议 left）
    highlight_keywords: 非空时在行内匹配并着色（长词优先；与 glow 不同时使用）
    background_top_y: 若指定（如 0），背景条从该 y 铺到原底边，用于主标题区顶到视频上沿。
    background_bottom_y: 若指定（如画布高度），背景下缘至少铺到该 y（不含），用于摘要区贴视频下沿。"""
    draw = ImageDraw.Draw(bg)
    hl_kw = [k.strip() for k in (highlight_keywords or []) if k and k.strip()]
    hl_pattern = _build_highlight_pattern(hl_kw) if hl_kw else None

    total_h = sum(
        draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] + line_spacing
        for line in lines
    )
    # 半透明背景（默认仅包住文字块上缘外 25px；background_top_y 可把上缘抬到画面顶部；
    # background_bottom_y 可把下缘延伸到画面底部）
    span_end = (start_y - 25) + (total_h + 40)
    if background_top_y is not None:
        bg_y = max(0, int(background_top_y))
    else:
        bg_y = start_y - 25
    if background_bottom_y is not None:
        span_end = max(span_end, int(background_bottom_y))
    _, ih = bg.size
    span_end = min(span_end, ih)
    bg_h = max(1, int(span_end - bg_y))
    overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(bg_h):
        p = i / bg_h
        alpha = int(220 * (min(p, 1 - p) / 0.1 if min(p, 1 - p) < 0.1 else 1))
        od.rectangle([(0, bg_y + i), (img_width, bg_y + i + 1)], fill=(20, 20, 40, alpha))
    result = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(result)

    cy = start_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_h = bbox[3] - bbox[1]

        use_hl = bool(hl_pattern) and not glow_color
        if use_hl:
            segs = _split_line_highlight_segments(line, hl_pattern)
            total_w = 0.0
            for seg, _ in segs:
                if not seg:
                    continue
                bb = draw.textbbox((0, 0), seg, font=font)
                total_w += bb[2] - bb[0]
            lw = total_w
        else:
            segs = None
            lw = bbox[2] - bbox[0]

        if align == "left":
            x = margin
        else:
            x = margin + (text_width - lw) // 2

        if use_hl and segs:
            _draw_text_line_shadow_segments(
                draw, float(x), float(cy), segs, font, text_color, highlight_color
            )
        elif glow_color:
            # 外层柔光（r=3）
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    d2 = dx * dx + dy * dy
                    if d2 <= 9:
                        a = int(50 * (1 - d2 / 9))
                        draw.text((x + dx, cy + dy), line, font=font,
                                  fill=(glow_color[0], glow_color[1], glow_color[2], a))
            draw.text((x + 3, cy + 3), line, font=font, fill=(0, 0, 0))
            draw.text((x + 1, cy + 1), line, font=font, fill=(10, 10, 30))
            draw.text((x, cy), line, font=font, fill=text_color)
        else:
            draw.text((x + 3, cy + 3), line, font=font, fill=(0, 0, 0))
            draw.text((x + 1, cy + 1), line, font=font, fill=(10, 10, 30))
            draw.text((x, cy), line, font=font, fill=text_color)
        cy += line_h + line_spacing

    return result, total_h


def _draw_subtitle_yellow_bar(
    bg,
    lines,
    font,
    start_y,
    img_width,
    margin,
    text_width,
    line_spacing=14,
    pad_x=18,
    pad_y=16,
    radius=12,
    bg_color=(255, 235, 59),
    text_color=(0, 0, 0),
):
    """副标题：黄色圆角背景、黑色文字垂直水平居中。"""
    if not lines:
        return bg, 0
    draw = ImageDraw.Draw(bg)
    cy = start_y
    total_block = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        x = margin + (text_width - lw) // 2
        x0, y0 = x - pad_x, cy - pad_y
        x1, y1 = x + lw + pad_x, cy + lh + pad_y
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=bg_color)
        cx = (x0 + x1) // 2
        cyy = (y0 + y1) // 2
        draw.text((cx, cyy), line, font=font, fill=text_color, anchor="mm")
        row_h = y1 - y0
        total_block += row_h + line_spacing
        cy = y1 + line_spacing
    return bg, total_block - line_spacing


def _subtitle_block_height(
    lines,
    font,
    draw_obj,
    pad_y=16,
    line_spacing=14,
):
    """与 _draw_subtitle_yellow_bar 一致的高度估算（用于布局预计算）。"""
    if not lines:
        return 0
    total = 0
    for line in lines:
        tb = draw_obj.textbbox((0, 0), line, font=font)
        lh = tb[3] - tb[1]
        total += lh + 2 * pad_y + line_spacing
    return max(0, total - line_spacing)