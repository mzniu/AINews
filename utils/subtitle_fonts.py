"""
字幕烧录用字体：系统字体名 + static/fonts/subtitle 下的自定义 TTF/OTF/TTC。

自定义字体文件放在 static/fonts/subtitle/，重启服务后出现在 /api/list-subtitle-fonts。
ASS 的 Fontname 必须与字体文件内的族名一致，故从字体内读取 name 表。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# 与 web_server 挂载 static 一致；FFmpeg 使用绝对路径更稳
SUBTITLE_CUSTOM_FONT_DIR = Path("static") / "fonts" / "subtitle"

# 内置选项（依赖服务器系统已安装；Windows 常见）
BUILTIN_SUBTITLE_FONTS: List[Dict[str, Any]] = [
    {"fontname": "Microsoft YaHei", "label": "微软雅黑（系统）", "source": "system"},
    {"fontname": "SimHei", "label": "黑体 SimHei（系统）", "source": "system"},
    {"fontname": "SimSun", "label": "宋体 SimSun（系统）", "source": "system"},
    {"fontname": "KaiTi", "label": "楷体 KaiTi（系统）", "source": "system"},
    {"fontname": "Microsoft JhengHei", "label": "微软正黑（系统）", "source": "system"},
    {"fontname": "DengXian", "label": "等线 DengXian（系统）", "source": "system"},
]


def _name_record_to_str(rec) -> str:
    try:
        if hasattr(rec, "toUnicode"):
            return rec.toUnicode()
    except Exception:
        pass
    s = rec.string
    if isinstance(s, bytes):
        for enc in ("utf-16-be", "utf-16-le", "utf-8", "latin-1"):
            try:
                return s.decode(enc)
            except Exception:
                continue
        return s.decode("latin-1", errors="replace")
    return str(s)


def font_family_name_from_file(font_path: Path) -> str:
    """从 TTF/OTF/TTC 读取适合作为 ASS Fontname 的族名（优先英文 Family）。"""
    font = None
    try:
        from fontTools.ttLib import TTFont

        try:
            font = TTFont(font_path, fontNumber=0)
        except Exception:
            font = TTFont(font_path)
        name_table = font.get("name")
        if not name_table:
            return font_path.stem.replace("_", " ")

        # 优先 Typographic Family (16)，再 Font Family (1)，再 Full name (4)
        preferred_ids = (16, 1, 4)
        candidates: List[tuple] = []
        for rec in name_table.names:
            if rec.nameID in preferred_ids:
                try:
                    text = _name_record_to_str(rec)
                    if text and text.strip():
                        candidates.append((rec.nameID, text.strip()))
                except Exception:
                    continue

        for nid in preferred_ids:
            for rid, text in candidates:
                if rid == nid:
                    return text

    except ImportError:
        logger.warning("未安装 fonttools，自定义字体将用文件名作为字体名（可能与 ASS 不匹配）")
    except Exception as e:
        logger.debug(f"解析字体名失败 {font_path}: {e}")
    finally:
        if font is not None:
            try:
                font.close()
            except Exception:
                pass

    return font_path.stem.replace("_", " ")


def list_custom_subtitle_font_files() -> List[Dict[str, Any]]:
    """扫描目录，返回供前端与烧录用条目。"""
    out: List[Dict[str, Any]] = []
    d = SUBTITLE_CUSTOM_FONT_DIR
    if not d.is_dir():
        return out

    exts = {".ttf", ".otf", ".ttc"}
    for p in sorted(d.iterdir()):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        if p.name.startswith("."):
            continue
        fname = font_family_name_from_file(p)
        rel = str(p).replace("\\", "/")
        out.append(
            {
                "fontname": fname,
                "label": f"{fname}（自定义 · {p.name}）",
                "source": "custom",
                "file": rel,
                "filename": p.name,
            }
        )
    return out


def subtitle_fonts_for_api() -> Dict[str, Any]:
    """合并系统预设与自定义文件。"""
    custom = list_custom_subtitle_font_files()
    fonts: List[Dict[str, Any]] = []
    for f in BUILTIN_SUBTITLE_FONTS:
        fonts.append({**f})
    for c in custom:
        fonts.append(c)
    return {
        "success": True,
        "fontsdir": str(SUBTITLE_CUSTOM_FONT_DIR.resolve()).replace("\\", "/"),
        "fonts": fonts,
    }


def resolved_fontsdir_for_ffmpeg() -> Optional[Path]:
    """若自定义目录存在则返回绝对路径，供 libass 加载。"""
    d = SUBTITLE_CUSTOM_FONT_DIR.resolve()
    if d.is_dir():
        return d
    return None
