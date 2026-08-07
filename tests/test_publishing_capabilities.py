def test_wechat_can_publish():
    from services.publishing.platform_capabilities import can_video_publish

    assert can_video_publish("wechat_channels") is True


def test_douyin_can_publish():
    from services.publishing.platform_capabilities import can_video_publish

    assert can_video_publish("douyin") is True


def test_douyin_can_account_login():
    from services.publishing.platform_capabilities import can_account_login

    assert can_account_login("douyin") is True


def test_xiaohongshu_can_publish():
    from services.publishing.platform_capabilities import can_video_publish

    assert can_video_publish("xiaohongshu") is True


def test_xiaohongshu_can_account_login():
    from services.publishing.platform_capabilities import can_account_login

    assert can_account_login("xiaohongshu") is True


def test_kuaishou_can_publish():
    from services.publishing.platform_capabilities import can_video_publish

    assert can_video_publish("kuaishou") is True


def test_kuaishou_can_account_login():
    from services.publishing.platform_capabilities import can_account_login

    assert can_account_login("kuaishou") is True
