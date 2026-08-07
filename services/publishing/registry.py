"""Platform registry and YAML loader."""

from __future__ import annotations



from typing import Any



import yaml



from services.publishing.adapters.base import PlatformAdapter

from src.utils.config import Config



PUBLISHING_CONFIG_PATH = Config.ROOT_DIR / "config" / "publishing_platforms.yaml"



ADAPTER_FACTORIES: dict[str, str] = {

    "wechat_channels": "services.publishing.adapters.wechat_channels:WechatChannelsAdapter",

    "douyin": "services.publishing.adapters.douyin:DouyinAdapter",

    "kuaishou": "services.publishing.adapters.kuaishou:KuaishouAdapter",

    "xiaohongshu": "services.publishing.adapters.xiaohongshu:XiaohongshuAdapter",

}





class PlatformDisabledError(ValueError):

    pass





class PlatformNotFoundError(ValueError):

    pass





def load_publishing_yaml() -> dict[str, Any]:

    if not PUBLISHING_CONFIG_PATH.exists():

        return {"platforms": [], "defaults": {}}

    with open(PUBLISHING_CONFIG_PATH, "r", encoding="utf-8") as handle:

        return yaml.safe_load(handle) or {}





def list_platforms() -> list[dict[str, Any]]:

    data = load_publishing_yaml()

    return list(data.get("platforms") or [])





def get_platform_config(platform_id: str) -> dict[str, Any]:

    for item in list_platforms():

        if item.get("id") == platform_id:

            return item

    raise PlatformNotFoundError(f"未知平台: {platform_id}")





def _import_adapter_class(adapter_key: str):

    target = ADAPTER_FACTORIES.get(adapter_key)

    if not target:

        raise PlatformNotFoundError(f"未实现的平台适配器: {adapter_key}")

    module_path, class_name = target.split(":")

    import importlib



    module = importlib.import_module(module_path)

    return getattr(module, class_name)





def build_adapter(cfg: dict[str, Any]) -> PlatformAdapter:

    defaults = load_publishing_yaml().get("defaults") or {}

    adapter_key = cfg.get("adapter", cfg["id"])

    factory = _import_adapter_class(adapter_key)

    return factory(

        platform_id=cfg["id"],

        display_name=cfg.get("display_name", cfg["id"]),

        login_url=cfg.get("login_url", ""),

        creator_url=cfg.get("creator_url", ""),

        upload_timeout_sec=int(defaults.get("upload_timeout_sec", 600)),

        qr_profile=cfg.get("qr_profile") or {},

        limits=cfg.get("limits") or {},

    )





def get_adapter(platform_id: str) -> PlatformAdapter:

    cfg = get_platform_config(platform_id)

    if not cfg.get("enabled", False):

        raise PlatformDisabledError(f"平台未启用: {platform_id}")

    return build_adapter(cfg)

