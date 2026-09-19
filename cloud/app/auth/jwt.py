from __future__ import annotations

from jose import JWTError, jwt

from app.config import Settings


class JWTAuthError(Exception):
    pass


def decode_access_token(token: str, settings: Settings) -> dict:
    secret = (settings.auth_jwt_secret or "").strip()
    if not secret:
        raise JWTAuthError("JWT secret not configured")
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as exc:
        raise JWTAuthError(str(exc)) from exc
    app_id = claims.get("app_id")
    expected = (settings.auth_app_id or "").strip()
    if app_id is not None and expected and str(app_id) != expected:
        raise JWTAuthError("Invalid app_id")
    sub = claims.get("sub")
    if not sub:
        raise JWTAuthError("Missing sub")
    return claims
