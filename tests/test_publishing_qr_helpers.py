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
