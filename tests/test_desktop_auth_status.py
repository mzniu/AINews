from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from services.desktop_auth_status import get_desktop_auth_status


def test_desktop_auth_status_missing_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    status = get_desktop_auth_status()
    assert status["authorized"] is False


def test_desktop_auth_status_online_phone_user(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(parents=True)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    (auth_dir / "session.json").write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "online",
                "app_id": "ainews",
                "access_token_sealed": "sealed-token",
                "expires_at": expires,
                "user": {
                    "user_id": "u1",
                    "email": "",
                    "phone": "13800138000",
                    "account_status": "active",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    status = get_desktop_auth_status()
    assert status["authorized"] is True
    assert status["phone"] == "13800138000"
    assert status["mode"] == "online"
