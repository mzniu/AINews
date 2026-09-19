from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_packs_root() -> Path:
    return Path(__file__).resolve().parents[2] / "packs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(default="sqlite:///./ainews_cloud.db", alias="DATABASE_URL")
    auth_jwt_secret: str = Field(default="", alias="AINEWS_AUTH_JWT_SECRET")
    auth_app_id: str = Field(default="app_ai_news", alias="AINEWS_AUTH_APP_ID")
    auth_jwks_url: str = Field(default="", alias="AINEWS_AUTH_JWKS_URL")
    packs_root: Path = Field(default_factory=_default_packs_root, alias="PACKS_ROOT")
    public_api_base: str = Field(
        default="https://ainews-api.xiaoniuliaoai.com",
        alias="PUBLIC_API_BASE",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
