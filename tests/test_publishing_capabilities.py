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


def test_can_post_first_comment_douyin():
    from services.publishing.platform_capabilities import can_post_first_comment

    assert can_post_first_comment("douyin") is True


def test_can_post_first_comment_kuaishou():
    from services.publishing.platform_capabilities import can_post_first_comment

    assert can_post_first_comment("kuaishou") is True


def test_can_post_first_comment_wechat():
    from services.publishing.platform_capabilities import can_post_first_comment

    assert can_post_first_comment("wechat_channels") is True


def test_can_post_first_comment_xiaohongshu():
    from services.publishing.platform_capabilities import can_post_first_comment

    assert can_post_first_comment("xiaohongshu") is True


def test_kuaishou_can_account_login():
    from services.publishing.platform_capabilities import can_account_login

    assert can_account_login("kuaishou") is True
