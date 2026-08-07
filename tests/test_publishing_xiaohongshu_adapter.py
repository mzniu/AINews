from services.publishing.registry import build_adapter, get_platform_config


def test_build_adapter_xiaohongshu_profile():
    cfg = get_platform_config("xiaohongshu")
    adapter = build_adapter(cfg)
    assert adapter.platform_id == "xiaohongshu"
    assert adapter.display_name == "小红书"
    assert cfg["capabilities"]["video_publish"] is True
    assert adapter.qr_profile.get("qr_switch_selector") == ".login-box-container img"
    assert "galaxy_creator_session_id" in adapter.qr_profile.get("required_session_cookies", [])


def test_xiaohongshu_adapter_overrides_publish_video():
    from services.publishing.adapters.creator_center import CreatorCenterAdapter
    from services.publishing.adapters.xiaohongshu import XiaohongshuAdapter

    cfg = get_platform_config("xiaohongshu")
    adapter = build_adapter(cfg)
    assert isinstance(adapter, XiaohongshuAdapter)
    assert adapter.publish_video is not CreatorCenterAdapter.publish_video


def test_get_adapter_xiaohongshu():
    from services.publishing.registry import get_adapter

    adapter = get_adapter("xiaohongshu")
    assert adapter.platform_id == "xiaohongshu"
