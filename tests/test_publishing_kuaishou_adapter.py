from services.publishing.registry import build_adapter, get_platform_config


def test_build_adapter_kuaishou_profile():
    cfg = get_platform_config("kuaishou")
    adapter = build_adapter(cfg)
    assert adapter.platform_id == "kuaishou"
    assert adapter.display_name == "快手"
    assert cfg["capabilities"]["video_publish"] is True
    assert adapter.qr_profile.get("qr_switch_selector") == "text=扫码登录"
    assert "kwssectoken" in adapter.qr_profile.get("required_session_cookies", [])


def test_kuaishou_adapter_overrides_publish_video():
    from services.publishing.adapters.creator_center import CreatorCenterAdapter
    from services.publishing.adapters.kuaishou import KuaishouAdapter

    cfg = get_platform_config("kuaishou")
    adapter = build_adapter(cfg)
    assert isinstance(adapter, KuaishouAdapter)
    assert adapter.publish_video is not CreatorCenterAdapter.publish_video


def test_get_adapter_kuaishou():
    from services.publishing.registry import get_adapter

    adapter = get_adapter("kuaishou")
    assert adapter.platform_id == "kuaishou"
