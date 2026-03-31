"""单元测试：动画视频标题解析（主标题两行 + 副标题单行 / 旧版 title）"""
import pytest
from PIL import Image, ImageDraw

from api.schemas.request_models import CreateAnimatedVideoRequest
from api.routes.video_routes import _resolve_animated_title_lines
from utils.video_utils import _load_fonts


@pytest.fixture
def draw_and_fonts():
    img = Image.new("RGB", (1080, 1920))
    d = ImageDraw.Draw(img)
    title_font, subtitle_font, _ = _load_fonts()
    return d, title_font, subtitle_font


def test_new_format_two_main_lines_and_subtitle(draw_and_fonts):
    d, tf, sf = draw_and_fonts
    req = CreateAnimatedVideoRequest(
        summary="x",
        images=[],
        main_line1="第一行主标题",
        main_line2="第二行主标题",
        subtitle="副标题单独一行",
    )
    main_lines, sub_lines = _resolve_animated_title_lines(req, d, tf, sf, 800)
    assert main_lines == ["第一行主标题", "第二行主标题"]
    assert sub_lines == ["副标题单独一行"]


def test_new_format_truncation(draw_and_fonts):
    d, tf, sf = draw_and_fonts
    req = CreateAnimatedVideoRequest(
        summary="x",
        images=[],
        main_line1="一二三四五六七八九十壹贰叁肆伍",  # 15 字 > MAIN_LINE_MAX_UNITS
        main_line2="",
        subtitle="副" * 20,
    )
    main_lines, sub_lines = _resolve_animated_title_lines(req, d, tf, sf, 800)
    assert len(main_lines[0]) == 14
    assert len(sub_lines[0]) == 16


def test_legacy_title_pipe(draw_and_fonts):
    d, tf, sf = draw_and_fonts
    req = CreateAnimatedVideoRequest(
        summary="x",
        images=[],
        title="这是较长的旧主标题可以换行|黄色副标题",
    )
    main_lines, sub_lines = _resolve_animated_title_lines(req, d, tf, sf, 800)
    assert len(main_lines) >= 1
    assert sub_lines  # 副标题有内容


def test_empty_new_falls_back_legacy(draw_and_fonts):
    d, tf, sf = draw_and_fonts
    req = CreateAnimatedVideoRequest(summary="x", images=[])
    main_lines, sub_lines = _resolve_animated_title_lines(req, d, tf, sf, 800)
    assert main_lines == ["未命名标题"]
    assert sub_lines == []
