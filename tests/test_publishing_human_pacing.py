from services.publishing import human_pacing


def test_human_pacing_ranges_cover_publish_steps():
    assert human_pacing._PAUSE_RANGES_MS["step"][0] >= 2000
    assert human_pacing._PAUSE_RANGES_MS["after_upload"][0] >= 3000
    assert human_pacing._PAUSE_RANGES_MS["before_publish"][0] >= 2500


def test_human_wait_scales_minimum(monkeypatch):
    calls: list[int] = []

    class FakePage:
        def wait_for_timeout(self, ms: int) -> None:
            calls.append(ms)

    monkeypatch.setattr(human_pacing, "_pacing_settings", lambda: (True, 1.5))
    human_pacing.human_wait(FakePage(), 1000)
    assert calls
    assert calls[0] >= 1500


def test_human_pause_disabled_uses_lower_bound(monkeypatch):
    calls: list[int] = []

    class FakePage:
        def wait_for_timeout(self, ms: int) -> None:
            calls.append(ms)

    monkeypatch.setattr(human_pacing, "_pacing_settings", lambda: (False, 1.0))
    human_pacing.human_pause(FakePage(), "step")
    assert calls == [2500]
