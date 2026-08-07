from services.publishing.registry import build_adapter, get_platform_config


def test_build_adapter_douyin_profile():
    cfg = get_platform_config("douyin")
    adapter = build_adapter(cfg)
    assert adapter.platform_id == "douyin"
    assert adapter.display_name == "抖音"
    assert "login" in adapter.qr_profile.get("success_url_excludes", [])
    assert cfg["capabilities"]["video_publish"] is True


def test_douyin_adapter_overrides_publish_video():
    from services.publishing.adapters.creator_center import CreatorCenterAdapter
    from services.publishing.adapters.douyin import DouyinAdapter

    cfg = get_platform_config("douyin")
    adapter = build_adapter(cfg)
    assert isinstance(adapter, DouyinAdapter)
    assert adapter.publish_video is not CreatorCenterAdapter.publish_video


def test_build_adapter_wechat():
    cfg = get_platform_config("wechat_channels")
    adapter = build_adapter(cfg)
    assert adapter.platform_id == "wechat_channels"
    assert adapter.login_url.startswith("https://channels.weixin.qq.com")
