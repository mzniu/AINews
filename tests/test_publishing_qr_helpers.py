from services.publishing.adapters.qr_helpers import is_login_success_url


def test_login_success_when_not_on_login_page():
    assert is_login_success_url(
        "https://creator.douyin.com/creator-micro/home",
        ["login", "passport"],
    )


def test_login_pending_on_login_page():
    assert not is_login_success_url(
        "https://creator.douyin.com/login",
        ["login", "passport"],
    )


def test_storage_state_has_session_cookies():
    from services.publishing.adapters.qr_helpers import storage_state_has_session_cookies

    storage = {"cookies": [{"name": "sessionid"}, {"name": "ttwid"}]}
    assert storage_state_has_session_cookies(storage, ("sessionid",))
    assert not storage_state_has_session_cookies(storage, ("sid_guard",))


def test_storage_state_accepts_any_required_cookie():
    from services.publishing.adapters.qr_helpers import storage_state_has_session_cookies

    storage = {"cookies": [{"name": "galaxy_creator_session_id"}]}
    required = ("galaxy_creator_session_id", "web_session")
    assert storage_state_has_session_cookies(storage, required)
    assert not storage_state_has_session_cookies({"cookies": []}, required)


def test_build_qr_login_profile_includes_stealth_defaults():
    from services.publishing.adapters.qr_helpers import build_qr_login_profile

    profile = build_qr_login_profile(
        platform_id="wechat_channels",
        login_url="https://channels.weixin.qq.com/login.html",
        creator_url="https://channels.weixin.qq.com/platform/post/create",
        qr_profile={"post_login_wait_ms": 6000},
    )
    assert profile.use_stealth_browser is True
    assert profile.cookie_settle_attempts == 15


def test_qr_selector_candidates_splits_comma_list():
    from services.publishing.adapters.qr_helpers import _qr_selector_candidates

    assert _qr_selector_candidates("img.a, img.b") == ["img.a", "img.b"]
    assert _qr_selector_candidates("img.js_qrcode_img.web_qrcode_img") == [
        "img.js_qrcode_img.web_qrcode_img"
    ]


def test_parse_qr_selector_supports_iframe_pipe_syntax():
    from services.publishing.adapters.qr_helpers import _parse_qr_selector

    assert _parse_qr_selector("iframe:#wx-oauth-container iframe|img.js_qrcode_img") == (
        "#wx-oauth-container iframe",
        "img.js_qrcode_img",
    )
    assert _parse_qr_selector("img.js_qrcode_img.web_qrcode_img") == (
        None,
        "img.js_qrcode_img.web_qrcode_img",
    )


def test_is_mobile_user_agent():
    from services.publishing.adapters.qr_helpers import _is_mobile_user_agent

    assert _is_mobile_user_agent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
    assert _is_mobile_user_agent("Mozilla/5.0 (Linux; Android 14; Pixel 7)")
    assert not _is_mobile_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
    )


def test_first_visible_locator_skips_hidden_nodes():
    from services.publishing.adapters.qr_helpers import _first_visible_locator

    class FakeItem:
        def __init__(self, visible: bool):
            self.visible = visible

        def is_visible(self, **kwargs):
            return self.visible

    class FakeLocator:
        def __init__(self, items):
            self._items = items

        def count(self):
            return len(self._items)

        def nth(self, index):
            return self._items[index]

    hidden = FakeItem(False)
    visible = FakeItem(True)
    loc = _first_visible_locator(FakeLocator([hidden, visible]), timeout_ms=500)
    assert loc is visible


def test_raise_qr_capture_error_wechat_mobile_redirect():
    from services.publishing.adapters.qr_helpers import _raise_qr_capture_error
    import pytest

    class FakePage:
        url = "https://channels.weixin.qq.com/mobile/mobile.html"

        def locator(self, selector):
            raise AssertionError("should not read body on mobile redirect")

    with pytest.raises(RuntimeError, match="移动端页面"):
        _raise_qr_capture_error(FakePage(), "img.qr")


def test_raise_qr_capture_error_wechat_oauth_load_failed():
    from services.publishing.adapters.qr_helpers import _raise_qr_capture_error
    import pytest

    class FakeBody:
        def inner_text(self, **kwargs):
            return "登录视频号助手\n加载失败，点击重试"

    class FakeIframeLoc:
        def first(self):
            return self

        def is_visible(self, **kwargs):
            return False

    class FakePage:
        url = "https://channels.weixin.qq.com/login.html"

        def locator(self, selector):
            if selector == "body":
                return FakeBody()
            return FakeIframeLoc()

    with pytest.raises(RuntimeError, match="OAuth 二维码加载失败"):
        _raise_qr_capture_error(FakePage(), "img.qr")


def test_capture_qr_downloads_img_src(monkeypatch, tmp_path):
    from services.publishing.adapters.qr_helpers import _capture_qr

    qr_path = tmp_path / "qr.png"
    body = b"fake-qr-bytes"

    class FakeResponse:
        ok = True

        @staticmethod
        def body():
            return body

    class FakeRequest:
        @staticmethod
        def get(url):
            assert url == "https://channels.weixin.qq.com/connect/qrcode/abc"
            return FakeResponse()

    class FakeLocator:
        def __init__(self):
            self.first = self

        def count(self):
            return 1

        def nth(self, index):
            assert index == 0
            return self

        def is_visible(self, **kwargs):
            return True

        def wait_for(self, **kwargs):
            return None

        def evaluate(self, script):
            return "https://channels.weixin.qq.com/connect/qrcode/abc"

        def screenshot(self, **kwargs):
            raise AssertionError("screenshot should not be called when download succeeds")

    class FakeFrame:
        def locator(self, selector):
            return FakeLocator()

    class FakeContext:
        request = FakeRequest()

    class FakePage:
        frames = [FakeFrame()]
        context = FakeContext()
        url = "https://example.com/login"

        def screenshot(self, **kwargs):
            raise AssertionError("full page screenshot should not be called")

        def wait_for_timeout(self, ms):
            return None

        def locator(self, selector):
            raise AssertionError(f"unexpected locator {selector}")

        def frame_locator(self, selector):
            raise AssertionError(f"unexpected frame_locator {selector}")

    _capture_qr(FakePage(), qr_path, "img.js_qrcode_img.web_qrcode_img")
    assert qr_path.read_bytes() == body


def test_capture_login_storage_state_snapshots_immediately_on_success_url():
    from services.publishing.adapters.qr_helpers import QrLoginProfile, _capture_login_storage_state

    storage = {"cookies": [{"name": "sessionid"}]}
    goto_calls = []

    class FakePage:
        url = "https://channels.weixin.qq.com/platform/post/create"

        def goto(self, url, **kwargs):
            goto_calls.append(url)

    class FakeContext:
        def storage_state(self):
            return storage

    profile = QrLoginProfile(
        platform_id="wechat_channels",
        login_url="https://channels.weixin.qq.com/login.html",
        success_url_excludes=["login", "passport"],
        post_login_url="https://channels.weixin.qq.com/platform/post/create",
    )
    result = _capture_login_storage_state(FakeContext(), FakePage(), profile)
    assert result == storage
    assert goto_calls == []


def test_capture_login_storage_state_skips_goto_when_already_on_settle_url():
    from services.publishing.adapters.qr_helpers import QrLoginProfile, _capture_login_storage_state

    settle = "https://channels.weixin.qq.com/platform/post/create"
    goto_calls = []

    class FakePage:
        url = settle

        def goto(self, url, **kwargs):
            goto_calls.append(url)

        def wait_for_timeout(self, ms):
            return None

    class FakeContext:
        def storage_state(self):
            return {"cookies": []}

    profile = QrLoginProfile(
        platform_id="wechat_channels",
        login_url="https://channels.weixin.qq.com/login.html",
        success_url_excludes=["login"],
        post_login_url=settle,
        use_stealth_browser=False,
        required_session_cookies=("sessionid",),
        cookie_settle_attempts=1,
    )
    _capture_login_storage_state(FakeContext(), FakePage(), profile)
    assert goto_calls == []


def test_is_target_closed_error():
    from services.publishing.adapters.qr_helpers import _is_target_closed_error

    class TargetClosedError(Exception):
        pass

    assert _is_target_closed_error(TargetClosedError("boom"))
    assert _is_target_closed_error(RuntimeError("Target page, context or browser has been closed"))
    assert not _is_target_closed_error(ValueError("other"))
