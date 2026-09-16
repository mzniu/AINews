from __future__ import annotations

import importlib.util
from pathlib import Path

import struct

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "desktop" / "scripts" / "generate-icons.py"


def _ico_layers(path: Path) -> dict[tuple[int, int], str]:
    data = path.read_bytes()
    _reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert kind == 1
    layers: dict[tuple[int, int], str] = {}
    for i in range(count):
        w, h, _c, _r, _p, _b, size, off = struct.unpack_from("<BBBBHHI I".replace(" ", ""), data, 6 + i * 16)
        w = 256 if w == 0 else w
        h = 256 if h == 0 else h
        payload = data[off : off + size]
        fmt = "PNG" if payload.startswith(b"\x89PNG") else "DIB"
        layers[(w, h)] = fmt
    return layers


def _load_mod():
    spec = importlib.util.spec_from_file_location("generate_icons", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_icon_corners_are_transparent() -> None:
    mod = _load_mod()
    img = mod.render_icon(32, opaque=True)
    assert img.getpixel((0, 0))[3] == 0
    assert img.getpixel((31, 0))[3] == 0
    assert img.getpixel((0, 31))[3] == 0
    assert img.getpixel((31, 31))[3] == 0
    assert img.getpixel((16, 16))[3] == 255


def test_ico_embeds_256_layer(tmp_path: Path) -> None:
    mod = _load_mod()
    ico_path = tmp_path / "icon.ico"
    mod.save_ico(ico_path)
    with Image.open(ico_path) as img:
        sizes = img.info.get("sizes") or set()
        assert (256, 256) in sizes
        assert (32, 32) in sizes
    assert ico_path.stat().st_size > 4000
    layers = _ico_layers(ico_path)
    assert layers[(16, 16)] == "DIB"
    assert layers[(32, 32)] == "DIB"
    assert layers[(256, 256)] == "PNG"
