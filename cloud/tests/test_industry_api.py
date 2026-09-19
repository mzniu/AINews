from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt

from app.config import get_settings
from app.main import app


def _auth_headers(user_id: str = "uc-test-1") -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": user_id,
            "app_id": settings.auth_app_id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.auth_jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_industry_taxonomy_lists_six_l2_paths():
    client = TestClient(app)
    response = client.get("/industry/taxonomy", headers=_auth_headers())
    assert response.status_code == 200
    paths = []
    for group in response.json().get("l1") or []:
        for item in group.get("l2") or []:
            paths.append(item["path"])
    assert len(paths) == 6
    assert "tech/ai" in paths


def test_pack_manifest_tech_ai():
    client = TestClient(app)
    response = client.get(
        "/industry-packs/tech/ai/manifest",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "tech/ai"
    assert "content_yaml" in body
    assert "大模型" in body["content_yaml"] or "industry:" in body["content_yaml"]


def test_put_active_industry_and_get_me():
    client = TestClient(app)
    headers = _auth_headers("uc-industry-user")
    put = client.put(
        "/me/active-industry",
        headers=headers,
        json={"active_industry_id": "finance/macro"},
    )
    assert put.status_code == 200
    assert put.json()["active_industry_id"] == "finance/macro"

    me = client.get("/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["active_industry_id"] == "finance/macro"
