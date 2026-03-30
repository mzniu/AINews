"""视频处理工具函数"""
import math
import random
import re
from typing import Tuple, List
from PIL import Image, ImageDraw, ImageFont
import numpy as np


def _load_fonts():
    """加载字体，返回 (title_font, subtitle_font, summary_font)"""
    try:
        return (ImageFont.truetype("msyhbd.ttc", 66),
                ImageFont.truetype("msyhbd.ttc", 58),
                ImageFont.truetype("msyh.ttc", 48))
    except:
        try:
            return (ImageFont.truetype("simhei.ttf", 66),
                    ImageFont.truetype("simhei.ttf", 58),
                    ImageFont.truetype("simhei.ttf", 48))
        except:
            df = ImageFont.load_default()
            return df, df, df


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


def _render_frame_animated(bg_template, user_img_resized, paste_x, final_paste_y,
                          target_width, target_height, img_width, img_height,
                          title_info, summary_info, t, entrance_duration=0.6,
                          hold_with_text_start=0.8, anim_type='zoom_in',
                          zoom_effect=False, zoom_start_scale=1.0, 
                          zoom_end_scale=1.15, clip_duration=None,
                          summary_scroll=False, summary_segments=None):
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
    summary_segments: 摘要分段信息 [(text1, y1), (text2, y2), (text3, y3)]
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
            # 向上滚动：从下方滑入
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
        # 小图已落定，应用持续放大效果（如果启用）
        if zoom_effect and clip_duration and clip_duration > entrance_duration:
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

    # --- 标题和摘要始终显示 ---
    if title_info and summary_info:
        t_font, st_font, main_lines, sub_lines, title_y, main_h, margin, text_width = title_info
        summary_font, summary_lines, summary_y = summary_info

        # 主标题：白色 + 蓝色光晕
        bg, _ = _draw_text_overlay(
            bg, main_lines, t_font, title_y, img_width, margin, text_width,
            text_color=(255, 255, 255), glow_color=(102, 126, 234), line_spacing=18
        )
        # 副标题：黄色，紧跟主标题下方
        if sub_lines:
            sub_y = title_y + main_h + 12
            bg, _ = _draw_text_overlay(
                bg, sub_lines, st_font, sub_y, img_width, margin, text_width,
                text_color=(255, 255, 0), glow_color=(180, 140, 30), line_spacing=14
            )
        
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
                        text_color=(255, 255, 255), line_spacing=12
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
        elif summary_scroll and summary_info:
            # 新逻辑：摘要整体滚动显示（不分段）
            scroll_start_time = entrance_duration + hold_with_text_start  # 约 1.4s
            scroll_duration = 1.2  # 整体滚动时间 1.2 秒
            
            # 计算滚动进度
            scroll_progress = (t - scroll_start_time) / scroll_duration
            scroll_progress = max(0.0, min(1.0, scroll_progress))  # 限制在 [0, 1]
            
            # 使用缓出曲线（从快到慢）
            ease = 1 - (1 - scroll_progress) ** 3
            
            # 计算透明度
            alpha = min(1.0, scroll_progress * 1.5)  # 更快达到不透明
            
            # 计算滑动偏移（从下方 80px 滑入）
            slide_offset = int(80 * (1 - ease))
            
            # 获取摘要信息
            summary_font_obj, summary_lines, summary_base_y = summary_info
            
            # 当前 Y 坐标（带动画）
            current_y = summary_base_y - slide_offset
            
            # 如果还在滚动中，应用透明度混合
            if scroll_progress < 1.0:
                # 绘制滚动中的摘要
                temp_bg, _ = _draw_text_overlay(
                    bg, summary_lines, summary_font_obj, current_y,
                    img_width, margin, text_width,
                    text_color=(255, 255, 255), line_spacing=12
                )
                
                # 应用透明度
                overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                temp_bg_rgba = temp_bg.convert('RGBA')
                for x in range(bg.width):
                    for y in range(bg.height):
                        orig_pixel = bg.getpixel((x, y))
                        new_pixel = temp_bg_rgba.getpixel((x, y))
                        r = int(orig_pixel[0] * (1 - alpha) + new_pixel[0] * alpha)
                        g = int(orig_pixel[1] * (1 - alpha) + new_pixel[1] * alpha)
                        b = int(orig_pixel[2] * (1 - alpha) + new_pixel[2] * alpha)
                        overlay.putpixel((x, y), (r, g, b, 255))
                bg = overlay.convert('RGB')
            else:
                # 滚动完成，直接绘制完整摘要
                bg, _ = _draw_text_overlay(
                    bg, summary_lines, summary_font_obj, summary_base_y,
                    img_width, margin, text_width,
                    text_color=(255, 255, 255), line_spacing=12
                )
        else:
            # 原始逻辑：一次性显示所有摘要
            bg, _ = _draw_text_overlay(
                bg, summary_lines, summary_font, summary_y, img_width, margin, text_width,
                text_color=(255, 255, 255), line_spacing=12
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
                      text_color=(255, 255, 255), glow_color=None, line_spacing=12):
    """在图片上绘制带半透明背景的文字块，返回 (result_image, block_height)"""
    draw = ImageDraw.Draw(bg)
    total_h = sum(
        draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] + line_spacing
        for line in lines
    )
    # 半透明背景
    bg_y = start_y - 25
    bg_h = total_h + 40
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
        lw = bbox[2] - bbox[0]
        x = margin + (text_width - lw) // 2
        if glow_color:
            # 外层柔光（r=3）
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    d2 = dx * dx + dy * dy
                    if d2 <= 9:
                        a = int(50 * (1 - d2 / 9))
                        draw.text((x + dx, cy + dy), line, font=font,
                                  fill=(glow_color[0], glow_color[1], glow_color[2], a))
        # 深色阴影
        draw.text((x + 3, cy + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x + 1, cy + 1), line, font=font, fill=(10, 10, 30))
        # 主文字
        draw.text((x, cy), line, font=font, fill=text_color)
        cy += bbox[3] - bbox[1] + line_spacing

    # 标题装饰：底部渐变高亮线
    if glow_color:
        accent_y = bg_y + bg_h - 4
        for i in range(3):
            alpha = 180 - i * 50
            for px in range(margin, img_width - margin):
                progress = (px - margin) / max(1, (img_width - 2 * margin))
                r = int(255 * (1 - progress) + glow_color[0] * progress)
                g = int(200 * (1 - progress) + glow_color[1] * progress)
                b = int(60 * (1 - progress) + glow_color[2] * progress)
                draw.point((px, accent_y + i), fill=(r, g, b, alpha))

    return result, total_h