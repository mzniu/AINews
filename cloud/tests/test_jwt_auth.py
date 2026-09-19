from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.auth.jwt import JWTAuthError, decode_access_token
from app.config import get_settings


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("AINEWS_AUTH_JWT_SECRET", "test-secret")
    monkeypatch.setenv("AINEWS_AUTH_APP_ID", "app_ai_news")
    get_settings.cache_clear()
    return get_settings()


def test_decode_valid_hs256_token(settings):
    payload = {
        "sub": "uc-user-1",
        "app_id": "app_ai_news",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "test-secret", algorithm="HS256")
    claims = decode_access_token(token, settings)
    assert claims["sub"] == "uc-user-1"


def test_rejects_expired_token(settings):
    payload = {
        "sub": "u1",
        "app_id": "app_ai_news",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=30),
    }
    token = jwt.encode(payload, "test-secret", algorithm="HS256")
    with pytest.raises(JWTAuthError):
        decode_access_token(token, settings)


def test_rejects_wrong_app_id(settings):
    payload = {
        "sub": "u1",
        "app_id": "app_other",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "test-secret", algorithm="HS256")
    with pytest.raises(JWTAuthError):
        decode_access_token(token, settings)
