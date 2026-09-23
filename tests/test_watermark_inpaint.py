from PIL import Image

from services.watermark_inpaint import inpaint_regions


class _FakeLama:
    def __call__(self, image, mask):
        return image.copy()


def test_inpaint_writes_sidecar(tmp_path, monkeypatch):
    src = tmp_path / "shot.jpg"
    Image.new("RGB", (80, 80), (10, 20, 30)).save(src)
    monkeypatch.setattr("services.watermark_inpaint.get_lama_model", lambda: _FakeLama())
    out = inpaint_regions(
        src,
        [{"x": 4, "y": 4, "width": 10, "height": 10}],
        output_stem_suffix="_auto_clean",
        expand_px=8,
        allow_mock=False,
    )
    assert out.name == "shot_auto_clean.jpg"
    assert out.parent.name == "watermark_removed"
    assert src.is_file()
    assert out.is_file()


def test_auto_path_rejects_mock(tmp_path, monkeypatch):
    src = tmp_path / "shot.jpg"
    Image.new("RGB", (40, 40), (1, 2, 3)).save(src)

    class MockLama:
        def __call__(self, image, mask):
            return image

    monkeypatch.setattr("services.watermark_inpaint.get_lama_model", lambda: MockLama())
    monkeypatch.setattr("services.watermark_inpaint.is_mock_lama", lambda _model: True)
    try:
        inpaint_regions(
            src,
            [{"x": 1, "y": 1, "width": 8, "height": 8}],
            output_stem_suffix="_auto_clean",
            allow_mock=False,
        )
    except RuntimeError as exc:
        assert "lama_unavailable" in str(exc)
    else:
        raise AssertionError("expected lama_unavailable")
    assert not (src.parent / "watermark_removed" / "shot_auto_clean.jpg").exists()
