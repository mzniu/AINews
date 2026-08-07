import pytest

from services.publishing.registry import PlatformNotFoundError, get_platform_config, list_platforms


def test_list_platforms_includes_wechat():
    platforms = list_platforms()
    assert any(p["id"] == "wechat_channels" for p in platforms)


def test_douyin_enabled():
    cfg = get_platform_config("douyin")
    assert cfg.get("enabled") is True


def test_get_adapter_douyin():
    from services.publishing.registry import get_adapter

    adapter = get_adapter("douyin")
    assert adapter.platform_id == "douyin"


def test_get_adapter_rejects_unknown_platform():
    from services.publishing.registry import PlatformNotFoundError, get_adapter

    with pytest.raises(PlatformNotFoundError):
        get_adapter("unknown_platform")
