"""Load/save language and vision model profiles for AINews."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from openai import OpenAI

from src.utils.config import Config

MODELS_TEMPLATE_PATH = Config.ROOT_DIR / "config" / "models.yaml"
MODELS_LOCAL_PATH = Config.ROOT_DIR / "config" / "models.local.yaml"

PROFILE_FIELDS = (
    "id",
    "display_name",
    "provider",
    "base_url",
    "model",
    "api_key",
    "max_tokens",
    "temperature",
    "enabled",
)


def _empty_section() -> dict[str, Any]:
    return {"active_id": None, "profiles": []}


def _default_local_config() -> dict[str, Any]:
    return {
        "version": 1,
        "language": _empty_section(),
        "vision": _empty_section(),
    }


def load_models_template() -> dict[str, Any]:
    if not MODELS_TEMPLATE_PATH.exists():
        return {}
    with open(MODELS_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _migrate_from_env(cfg: dict[str, Any]) -> dict[str, Any]:
    """Seed language profile from legacy .env on first run."""
    lang = cfg.setdefault("language", _empty_section())
    if lang.get("profiles"):
        return cfg

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key == "your_deepseek_api_key_here":
        return cfg

    profile_id = "deepseek_env"
    lang["profiles"] = [
        {
            "id": profile_id,
            "display_name": "DeepSeek（来自 .env）",
            "provider": "deepseek",
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "api_key": api_key,
            "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192")),
            "temperature": 0.7,
            "enabled": True,
        }
    ]
    lang["active_id"] = profile_id
    return cfg


def load_models_config(*, migrate_env: bool = True) -> dict[str, Any]:
    cfg = _default_local_config()
    if MODELS_LOCAL_PATH.exists():
        with open(MODELS_LOCAL_PATH, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if isinstance(loaded, dict):
            cfg.update(loaded)
            cfg.setdefault("language", _empty_section())
            cfg.setdefault("vision", _empty_section())

    if migrate_env:
        cfg = _migrate_from_env(cfg)
        if not MODELS_LOCAL_PATH.exists() and cfg.get("language", {}).get("profiles"):
            save_models_config(cfg)

    return cfg


def save_models_config(cfg: dict[str, Any]) -> None:
    MODELS_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": cfg.get("version", 1),
        "language": cfg.get("language") or _empty_section(),
        "vision": cfg.get("vision") or _empty_section(),
    }
    with open(MODELS_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, allow_unicode=True, sort_keys=False)


def mask_api_key(api_key: str | None) -> str:
    key = (api_key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "********"
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


def _normalize_profile(raw: dict[str, Any], *, kind: str) -> dict[str, Any]:
    template = load_models_template()
    defaults = (template.get("defaults") or {}).get(kind) or {}
    provider = str(raw.get("provider") or "deepseek")
    provider_cfg = (template.get("providers") or {}).get(provider) or {}

    profile = {
        "id": str(raw.get("id") or "").strip(),
        "display_name": str(raw.get("display_name") or raw.get("model") or "未命名").strip(),
        "provider": provider,
        "base_url": (
            str(raw.get("base_url")).strip()
            if raw.get("base_url") is not None and str(raw.get("base_url")).strip()
            else str(provider_cfg.get("default_base_url") or "https://api.deepseek.com").strip()
        ),
        "model": str(raw.get("model") or "deepseek-chat").strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
        "max_tokens": int(raw.get("max_tokens") or defaults.get("max_tokens") or 8192),
        "temperature": float(raw.get("temperature") if raw.get("temperature") is not None else defaults.get("temperature", 0.7)),
        "enabled": bool(raw.get("enabled", True)),
    }
    return profile


def _find_profile(section: dict[str, Any], profile_id: str | None) -> dict[str, Any] | None:
    profiles = section.get("profiles") or []
    if not profile_id:
        return None
    for item in profiles:
        if item.get("id") == profile_id:
            return item
    return None


def get_active_profile(kind: str) -> dict[str, Any] | None:
    cfg = load_models_config()
    section = cfg.get(kind) or _empty_section()
    active_id = section.get("active_id")
    profile = _find_profile(section, active_id)
    if profile and profile.get("enabled", True) and profile.get("api_key"):
        return _normalize_profile(profile, kind=kind)
    for item in section.get("profiles") or []:
        if item.get("enabled", True) and item.get("api_key"):
            return _normalize_profile(item, kind=kind)
    return None


def get_active_language_profile() -> dict[str, Any] | None:
    return get_active_profile("language")


def get_active_vision_profile() -> dict[str, Any] | None:
    return get_active_profile("vision")


def build_openai_client(profile: dict[str, Any] | None) -> OpenAI | None:
    if not profile:
        return None
    api_key = profile.get("api_key", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url=profile.get("base_url"))


def get_language_client() -> tuple[OpenAI | None, dict[str, Any] | None]:
    profile = get_active_language_profile()
    return build_openai_client(profile), profile


def get_vision_client() -> tuple[OpenAI | None, dict[str, Any] | None]:
    profile = get_active_vision_profile()
    return build_openai_client(profile), profile


def public_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = copy.deepcopy(cfg or load_models_config())
    template = load_models_template()
    for kind in ("language", "vision"):
        section = raw.setdefault(kind, _empty_section())
        public_profiles = []
        for item in section.get("profiles") or []:
            prof = _normalize_profile(item, kind=kind)
            prof["api_key_masked"] = mask_api_key(prof.get("api_key"))
            prof.pop("api_key", None)
            public_profiles.append(prof)
        section["profiles"] = public_profiles
    return {
        "version": raw.get("version", 1),
        "language": raw["language"],
        "vision": raw["vision"],
        "providers": template.get("providers") or {},
        "language_presets": template.get("language_presets") or [],
        "vision_presets": template.get("vision_presets") or [],
        "defaults": template.get("defaults") or {},
        "config_path": str(MODELS_LOCAL_PATH),
        "has_local_file": MODELS_LOCAL_PATH.exists(),
    }


def merge_incoming_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_models_config(migrate_env=False)
    merged = _default_local_config()
    merged["version"] = payload.get("version", 1)

    for kind in ("language", "vision"):
        incoming = payload.get(kind) or {}
        prev_section = current.get(kind) or _empty_section()
        prev_by_id = {p.get("id"): p for p in prev_section.get("profiles") or [] if p.get("id")}

        profiles: list[dict[str, Any]] = []
        for raw in incoming.get("profiles") or []:
            prof = _normalize_profile(raw, kind=kind)
            if not prof["id"]:
                continue
            new_key = (raw.get("api_key") or "").strip()
            if not new_key:
                prev = prev_by_id.get(prof["id"]) or {}
                prof["api_key"] = str(prev.get("api_key") or "")
            else:
                prof["api_key"] = new_key
            profiles.append(prof)

        merged[kind] = {
            "active_id": incoming.get("active_id"),
            "profiles": profiles,
        }

    return merged


def test_language_model() -> dict[str, Any]:
    client, profile = get_language_client()
    if client is None or profile is None:
        return {"success": False, "message": "未配置可用的语言模型（请填写 API Key 并启用）"}
    try:
        resp = client.chat.completions.create(
            model=profile["model"],
            messages=[{"role": "user", "content": "回复 OK"}],
            max_tokens=16,
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        return {
            "success": True,
            "message": f"语言模型可用：{profile['display_name']} / {profile['model']}",
            "reply": text[:100],
        }
    except Exception as exc:
        return {"success": False, "message": f"语言模型测试失败：{exc}"}


def test_vision_model() -> dict[str, Any]:
    client, profile = get_vision_client()
    if client is None or profile is None:
        return {"success": False, "message": "未配置可用的视觉模型（请填写 API Key 并启用）"}
    try:
        resp = client.chat.completions.create(
            model=profile["model"],
            messages=[
                {
                    "role": "user",
                    "content": "你是一个视觉理解模型。请仅回复 VISION_OK。",
                }
            ],
            max_tokens=32,
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        return {
            "success": True,
            "message": f"视觉模型可用：{profile['display_name']} / {profile['model']}",
            "reply": text[:100],
        }
    except Exception as exc:
        return {"success": False, "message": f"视觉模型测试失败：{exc}"}
