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


def test_new_format_two_subtitle_lines(draw_and_fonts):
    d, tf, sf = draw_and_fonts
    req = CreateAnimatedVideoRequest(
        summary="x",
        images=[],
        main_line1="主标题第一行",
        main_line2="主标题第二行",
        subtitle="副标题第一行",
        subtitle2="副标题第二行流量钩子",
    )
    main_lines, sub_lines = _resolve_animated_title_lines(req, d, tf, sf, 800)
    assert main_lines == ["主标题第一行", "主标题第二行"]
    assert sub_lines == ["副标题第一行", "副标题第二行流量钩子"]


def test_subtitle2_empty_is_skipped(draw_and_fonts):
    d, tf, sf = draw_and_fonts
    req = CreateAnimatedVideoRequest(
        summary="x",
        images=[],
        main_line1="主标题第一行",
        subtitle="只有第一行副标题",
        subtitle2="",
    )
    main_lines, sub_lines = _resolve_animated_title_lines(req, d, tf, sf, 800)
    assert sub_lines == ["只有第一行副标题"]


def test_new_format_passes_through_untruncated(draw_and_fonts):
    d, tf, sf = draw_and_fonts
    req = CreateAnimatedVideoRequest(
        summary="x",
        images=[],
        # 超长输入：服务端不再截断，原样回传
        main_line1="一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾",
        main_line2="",
        subtitle="副" * 20,
    )
    main_lines, sub_lines = _resolve_animated_title_lines(req, d, tf, sf, 800)
    assert main_lines[0] == "一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾"
    assert len(sub_lines[0]) == 20


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
