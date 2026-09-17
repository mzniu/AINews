# AINews Cloud Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec (v1.1):** [2026-09-04-desktop-cloud-subscription-design.md](../specs/2026-09-04-desktop-cloud-subscription-design.md)  
**Errata (mandatory):** [2026-09-17-usercenter-cloud-integration-errata.md](../specs/2026-09-17-usercenter-cloud-integration-errata.md)  
**Legacy plan (desktop / P0–P2 / auth — do not re-implement):** [2026-09-04-desktop-cloud-subscription.md](./2026-09-04-desktop-cloud-subscription.md)

**Goal:** Ship the **AINews Cloud Control Plane** (`cloud/`): UserCenter JWT gate, PostgreSQL tenant data, subscriptions/entitlements, and config sync APIs — plus **desktop/Python integration** for entitlements cache and route guards (P5 slice).

**Architecture:** Monolithic **FastAPI** service under `cloud/` with **PostgreSQL**. **No** Cloud auth routes; every business handler runs behind **Bearer JWT** validation (`AINEWS_AUTH_JWT_SECRET` or `AINEWS_AUTH_JWKS_URL`), `app_id` claim check, and **`get_or_create_personal_workspace(usercenter_user_id)`**. Desktop **UserCenter login is already implemented** (`desktop/src-tauri/src/auth/`); Tauri passes the same access token to Cloud.

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2.x · Alembic · PostgreSQL 15+ · `python-jose[cryptography]` · PyJWT (optional alt) · PyYAML · pytest · httpx · Testcontainers or docker-compose for PG in CI

## Global Constraints

- **Identity:** UserCenter only (`app_ai_news`); Cloud **must not** implement `POST /auth/register|login|refresh|logout` (see errata).
- **JWT:** HS256 via `AINEWS_AUTH_JWT_SECRET` **or** RS256 via `AINEWS_AUTH_JWKS_URL`; validate `exp`; if `app_id` present → must equal `AINEWS_AUTH_APP_ID` (default `app_ai_news`).
- **Schema:** `usercenter_accounts` + `owner_usercenter_id`; **no** `password_hash` / `users` table.
- **V1 billing:** Manual `subscriptions` rows / `cloud/scripts/set_plan.py`; **no payment webhooks** in this plan.
- **Config sync:** Only §6.1 whitelist keys; Free plan → sync APIs return **403**.
- **Entitlements:** Response shape §7.2; `extensions.multi_industry` **M0 = `null` only** (no industry pack loader).
- **Offline grace:** `offline_grace_until` computed from plan (`free` 3d, `pro`/`team` 7d) per §7.1.
- **Cloud production:** No `AINES_DEV_MODE` bypass on Cloud (dev bypass remains **local Python only** per spec §8.3).
- **Prerequisite gate:** P0 paths + P1 Tauri MVP per spec §10 before freezing public Cloud API shapes (this plan assumes those gates are tracked in the legacy plan).

---

## Scope

| In scope | Owner phase |
|----------|-------------|
| `cloud/` service scaffold, Docker PG, Alembic | P3 |
| JWT middleware + tenant lazy-create | P3 |
| `GET /me`, `GET /subscription`, `GET /entitlements` | P3 |
| `GET/PUT /sync/config/*` manifest + blobs | P4 |
| Admin script `set_plan.py` (by `usercenter_user_id`) | P3 |
| Appendix B JWT tests (expiry, wrong `app_id`, lazy-create idempotency) | P3 |
| Local `services/entitlements/*`, route guards, Tauri refresh of entitlements | P5 |
| Minimal `extensions.multi_industry: null` in API + one schema test | P3 |

## Non-goals

- **Duplicate UserCenter auth** (register/login/JWT issuance on Cloud).
- **Payment webhooks**, Stripe/WeChat, auto-provisioning from payments (P6 / separate plan).
- **Organization / team UI**, SSO, seat management.
- **Content/video/SQLite** upload to Cloud.
- **Industry pack loader** or non-null `multi_industry` behavior (M0 placeholder only).
- **P0–P2 desktop packaging**, **P6** updater/signing (see legacy plan).
- **macOS** desktop (spec open question).

## Prerequisites

1. **UserCenter** app registered: `AINEWS_AUTH_APP_ID=app_ai_news`; JWT signing secret or JWKS reachable from Cloud.
2. **Desktop auth done:** `desktop/src-tauri/src/auth/` (`AuthClient`, token storage) — login/refresh against UserCenter, not Cloud.
3. **Spec v1.1** merged or linked on branch (PR [#11](https://github.com/mzniu/AINews/pull/11) `cursor/usercenter-cloud-spec-v1.1`).
4. **Legacy plan P0/P1** (or equivalent): `src/utils/paths.py`, Tauri MVP — before production Cloud deploy; Cloud development can proceed in parallel using docker-compose PG.
5. **Ops:** VPS + TLS for `api.*` (deployment task stubbed in P3 gate only).

## Auth / desktop tasks (reference only)

Per [errata](../specs/2026-09-17-usercenter-cloud-integration-errata.md), **do not** implement legacy plan **Task 11** (`cloud/app/routers/auth.py`) or **Task 13** cloud-login variants. Use:

- UserCenter: `POST /v1/auth/*`, `GET /v1/users/me`
- Desktop: existing `auth/client.rs`, `auth/config.rs` env defaults
- Cloud: JWT middleware only (this plan **Task 4–6**)

---

## File Map (`cloud/`)

| Path | Responsibility |
|------|----------------|
| `cloud/requirements.txt` | FastAPI, SQLAlchemy, alembic, jose, psycopg2, pyyaml |
| `cloud/docker-compose.yml` | PostgreSQL 15 dev |
| `cloud/.env.example` | `DATABASE_URL`, `AINEWS_AUTH_*` |
| `cloud/app/main.py` | App factory, router mount, `/health` (unauthenticated) |
| `cloud/app/config.py` | Pydantic settings from env |
| `cloud/app/database.py` | Engine, session |
| `cloud/app/models/` | ORM: accounts, workspaces, subscriptions, config_blobs, devices |
| `cloud/app/auth/jwt.py` | Verify HS256/JWKS, extract claims |
| `cloud/app/auth/middleware.py` | Optional: request state; prefer `deps.py` dependency |
| `cloud/app/deps.py` | `get_bearer_token`, `get_current_usercenter_id`, `get_current_workspace` |
| `cloud/app/services/tenant.py` | `get_or_create_personal_workspace` |
| `cloud/app/services/plans.py` | Plan limits + grace days |
| `cloud/app/services/entitlements.py` | Build §7.2 payload |
| `cloud/app/routers/me.py` | `GET /me` |
| `cloud/app/routers/subscription.py` | `GET /subscription` |
| `cloud/app/routers/entitlements.py` | `GET /entitlements` |
| `cloud/app/routers/config_sync.py` | `/sync/config/*` |
| `cloud/app/sync/keys.py` | `SYNC_CONFIG_KEYS` whitelist |
| `cloud/alembic/versions/001_initial.py` | §5.2 schema |
| `cloud/scripts/set_plan.py` | CLI: set plan by usercenter id |
| `cloud/tests/conftest.py` | TestClient, PG fixture, JWT test helper |
| `cloud/tests/test_jwt_auth.py` | Appendix B security tests |
| `cloud/tests/test_tenant_lazy_create.py` | Idempotency |
| `cloud/tests/test_me.py` | `/me` |
| `cloud/tests/test_entitlements.py` | `/entitlements` + `extensions` |
| `cloud/tests/test_config_sync.py` | Sync routes |

**P5 (repo root, not under `cloud/`):**

| Path | Responsibility |
|------|----------------|
| `services/entitlements/cache.py` | Read `%APPDATA%/AINews/cache/entitlements.json` |
| `services/entitlements/guard.py` | `check_entitlement(feature)` |
| `services/entitlements/errors.py` | `EntitlementError` |
| `tests/test_entitlements_guard.py` | Guard unit tests |
| `desktop/src-tauri/src/cloud.rs` (or extend `main.rs`) | `GET {CLOUD}/entitlements` with UC token → write cache |
| `api/routes/entitlements_routes.py` | `GET /api/entitlements/status` (local cache) |

---

## Phase P3 — Cloud: JWT + DB + entitlements

**Phase gate:** From clean `docker compose up`, with a test-signed JWT: `GET /me` → workspace id; `GET /entitlements` → `plan_id: free`, `extensions.multi_industry: null`; Appendix B tests green.

```bash
cd cloud && docker compose up -d && pip install -r requirements.txt && alembic upgrade head
pytest cloud/tests/test_jwt_auth.py cloud/tests/test_tenant_lazy_create.py cloud/tests/test_entitlements.py -v
```

**Manual smoke:** Issue real UserCenter token (staging) → `curl -H "Authorization: Bearer $TOKEN" http://localhost:8090/entitlements`.

---

### Task 1: Cloud scaffold + health

**Files:**
- Create: `cloud/requirements.txt`, `cloud/docker-compose.yml`, `cloud/.env.example`
- Create: `cloud/app/__init__.py`, `cloud/app/main.py`, `cloud/app/config.py`
- Test: `cloud/tests/test_health.py`

**Interfaces:**
- Produces: `app: FastAPI` with `GET /health` → `{"status":"ok"}` (no auth)

- [ ] **Step 1: Write failing test**

```python
# cloud/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app

def test_health_unauthenticated():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd cloud && PYTHONPATH=. pytest tests/test_health.py -v`  
Expected: FAIL (`app.main` missing)

- [ ] **Step 3: Implement minimal app**

```python
# cloud/app/main.py
from fastapi import FastAPI

app = FastAPI(title="AINews Cloud", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd cloud && PYTHONPATH=. pytest tests/test_health.py -v`

- [ ] **Step 5: Commit**

```bash
git add cloud/
git commit -m "feat(cloud): scaffold FastAPI service and health endpoint"
```

---

### Task 2: Settings + database session

**Files:**
- Create: `cloud/app/database.py`
- Modify: `cloud/app/config.py`
- Test: `cloud/tests/test_database.py`

**Interfaces:**
- Produces: `get_db()` generator; `Settings` with `database_url`, `auth_app_id`, `auth_jwt_secret`, `auth_jwks_url`

- [ ] **Step 1: Failing test (session rolls back)**

```python
# cloud/tests/test_database.py
import os
from sqlalchemy import text
from app.database import SessionLocal

def test_database_connects():
    url = os.environ.get("DATABASE_URL", "postgresql://ainews:ainews@localhost:5432/ainews_cloud")
    if not url:
        import pytest
        pytest.skip("DATABASE_URL not set")
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT 1")).scalar() == 1
    finally:
        db.close()
```

- [ ] **Step 2: Run — FAIL until database.py exists**

- [ ] **Step 3: Implement `config.py` + `database.py` (SQLAlchemy 2.0)**

- [ ] **Step 4: PASS with `docker compose up -d`**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): database session and settings"
```

---

### Task 3: Alembic migration — spec §5.2 schema

**Files:**
- Create: `cloud/app/models/__init__.py`, `usercenter_account.py`, `workspace.py`, `subscription.py`, `config_blob.py`, `device.py`
- Create: `cloud/alembic/env.py`, `cloud/alembic/versions/001_initial_usercenter.py`
- Test: `cloud/tests/test_schema.py`

**Interfaces:**
- Produces: tables `usercenter_accounts`, `workspaces`, `workspace_members`, `subscriptions`, `config_blobs`, `devices` per spec §5.2 (no `users`, no `password_hash`)

- [ ] **Step 1: Failing test — tables exist after upgrade**

```python
# cloud/tests/test_schema.py
from sqlalchemy import inspect
from app.database import engine

def test_usercenter_accounts_table_exists():
    insp = inspect(engine)
    assert "usercenter_accounts" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("usercenter_accounts")}
    assert "usercenter_user_id" in cols
    assert "password_hash" not in cols
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: ORM + migration SQL aligned to spec §5.2**

- [ ] **Step 4: `alembic upgrade head` + pytest PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): usercenter_accounts schema migration"
```

---

### Task 4: JWT verification helper (HS256 test secret)

**Files:**
- Create: `cloud/app/auth/jwt.py`
- Test: `cloud/tests/test_jwt_verify.py`

**Interfaces:**
- Produces: `decode_access_token(token: str, settings: Settings) -> dict` raising `JWTAuthError` on failure

- [ ] **Step 1: Failing test — valid token**

```python
# cloud/tests/test_jwt_verify.py
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.auth.jwt import decode_access_token
from app.config import get_settings

def test_decode_valid_hs256_token(monkeypatch):
    secret = "test-secret"
    monkeypatch.setenv("AINEWS_AUTH_JWT_SECRET", secret)
    monkeypatch.setenv("AINEWS_AUTH_APP_ID", "app_ai_news")
    get_settings.cache_clear()
    payload = {
        "sub": "uc-user-1",
        "app_id": "app_ai_news",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    claims = decode_access_token(token, get_settings())
    assert claims["sub"] == "uc-user-1"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `decode_access_token` (exp + app_id when present)**

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): JWT decode and claim validation"
```

---

### Task 5: Appendix B — expired token and wrong `app_id`

**Files:**
- Modify: `cloud/app/auth/jwt.py`
- Test: `cloud/tests/test_jwt_auth.py` (chief architect blocking tests)

**Interfaces:**
- Consumes: `decode_access_token`
- Produces: same; used by `deps.py`

- [ ] **Step 1: Failing tests**

```python
# cloud/tests/test_jwt_auth.py
from datetime import datetime, timedelta, timezone
import pytest
from jose import jwt
from app.auth.jwt import decode_access_token, JWTAuthError
from app.config import get_settings

@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("AINEWS_AUTH_JWT_SECRET", "test-secret")
    monkeypatch.setenv("AINEWS_AUTH_APP_ID", "app_ai_news")
    get_settings.cache_clear()
    return get_settings()

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
```

- [ ] **Step 2: Run — FAIL if not implemented**

Run: `cd cloud && PYTHONPATH=. pytest tests/test_jwt_auth.py -v`

- [ ] **Step 3: Enforce `exp` and `app_id == settings.auth_app_id`**

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "test(cloud): JWT expiry and app_id validation (appendix B)"
```

---

### Task 6: Lazy-create personal workspace (idempotent)

**Files:**
- Create: `cloud/app/services/tenant.py`
- Test: `cloud/tests/test_tenant_lazy_create.py`

**Interfaces:**
- Produces: `get_or_create_personal_workspace(db, usercenter_user_id: str, email: str | None) -> Workspace`

- [ ] **Step 1: Failing test — double call one row**

```python
# cloud/tests/test_tenant_lazy_create.py
from app.database import SessionLocal
from app.services.tenant import get_or_create_personal_workspace
from app.models.workspace import Workspace

def test_lazy_create_is_idempotent():
    db = SessionLocal()
    try:
        w1 = get_or_create_personal_workspace(db, "uc-42", email="a@b.com")
        w2 = get_or_create_personal_workspace(db, "uc-42", email="a@b.com")
        assert w1.id == w2.id
        count = db.query(Workspace).filter(Workspace.owner_usercenter_id == "uc-42").count()
        assert count == 1
    finally:
        db.close()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement: upsert `usercenter_accounts`, create `personal` workspace + member + default `free` subscription if missing**

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): idempotent personal workspace lazy-create"
```

---

### Task 7: Auth dependency + protected route stub

**Files:**
- Create: `cloud/app/deps.py`
- Modify: `cloud/app/main.py` (include routers later)
- Test: `cloud/tests/test_deps_auth.py`

**Interfaces:**
- Produces: `CurrentContext` dataclass: `usercenter_user_id`, `workspace_id`
- `require_auth` FastAPI dependency → 401 without Bearer, 403 on bad JWT

- [ ] **Step 1: Failing test — missing header**

```python
# cloud/tests/test_deps_auth.py
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from app.deps import require_auth

mini = FastAPI()

@mini.get("/protected")
def protected(ctx=Depends(require_auth)):
    return {"workspace_id": str(ctx.workspace_id)}

def test_missing_bearer_401():
    client = TestClient(mini)
    assert client.get("/protected").status_code == 401
```

- [ ] **Step 2–4: Implement `require_auth` wiring JWT + tenant service**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): Bearer auth dependency and workspace context"
```

---

### Task 8: `GET /me`

**Files:**
- Create: `cloud/app/routers/me.py`
- Modify: `cloud/app/main.py`
- Test: `cloud/tests/test_me.py`

**Interfaces:**
- Produces: `GET /me` → `{ usercenter_user_id, email?, workspace: { id, type, name } }`

- [ ] **Step 1: Failing test with signed JWT**

```python
# cloud/tests/test_me.py
from datetime import datetime, timedelta, timezone
from jose import jwt
from fastapi.testclient import TestClient
from app.main import app

def test_me_returns_workspace(auth_headers):
    client = TestClient(app)
    r = client.get("/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["workspace"]["type"] == "personal"
    assert "id" in body["workspace"]
```

(Add `auth_headers` fixture in `cloud/tests/conftest.py` that mints HS256 token.)

- [ ] **Step 2–4: Router + lazy-create on first hit**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): GET /me tenant context"
```

---

### Task 9: Plans service + `GET /subscription`

**Files:**
- Create: `cloud/app/services/plans.py`
- Create: `cloud/app/routers/subscription.py`
- Test: `cloud/tests/test_subscription.py`

**Interfaces:**
- Produces: `GET /subscription` → `{ plan_id, status, current_period_end }`

- [ ] **Step 1: Failing test — new user defaults free/active**

- [ ] **Step 3: `PLANS` dict per legacy plan Task 12 / spec §7.1**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): GET /subscription"
```

---

### Task 10: `GET /entitlements` + M0 `extensions.multi_industry`

**Files:**
- Create: `cloud/app/services/entitlements.py`
- Create: `cloud/app/routers/entitlements.py`
- Test: `cloud/tests/test_entitlements.py`

**Interfaces:**
- Produces: `GET /entitlements` full §7.2 shape; `extensions.multi_industry` always `null` in V1

- [ ] **Step 1: Failing test**

```python
# cloud/tests/test_entitlements.py
def test_entitlements_includes_multi_industry_placeholder(auth_client):
    r = auth_client.get("/entitlements")
    assert r.status_code == 200
    data = r.json()
    assert data["extensions"]["multi_industry"] is None
    assert "offline_grace_until" in data
    assert data["limits"]["ai_summaries_per_month"] == 20  # free default
```

- [ ] **Step 3: Compute `offline_grace_until` from `current_period_end` + plan grace days**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): GET /entitlements with multi_industry M0 stub"
```

---

### Task 11: `cloud/scripts/set_plan.py`

**Files:**
- Create: `cloud/scripts/set_plan.py`
- Test: `cloud/tests/test_set_plan_script.py`

**Interfaces:**
- CLI: `--usercenter-user-id uc-42 --plan pro --status active`

- [ ] **Step 1: Test updates subscription row and entitlements reflect plan**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): manual plan setter for ops"
```

---

### Task 12: JWKS code path (optional RS256) — stub task

**Files:**
- Modify: `cloud/app/auth/jwt.py`
- Test: `cloud/tests/test_jwt_jwks.py`

**Interfaces:**
- If `AINEWS_AUTH_JWKS_URL` set and secret empty, fetch JWKS (cache keys in memory for tests use mock httpx).

- [ ] **Step 1: Skip test if only HS256 used in CI**

```python
def test_jwks_path_used_when_configured(monkeypatch, httpx_mock):
    pytest.importorskip("respx")  # or httpx mock
    ...
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): optional JWKS verification path"
```

---

## Phase P4 — Config sync (Cloud API)

**Phase gate:**

```bash
cd cloud && PYTHONPATH=. pytest tests/test_config_sync.py -v
```

Free plan → `PUT /sync/config/content_prompts.local` → **403**; Pro (via `set_plan.py`) → **200**; manifest lists keys.

**Manual smoke:** `curl -H "Authorization: Bearer $TOKEN" http://localhost:8090/sync/config/manifest`

---

### Task 13: Sync whitelist module

**Files:**
- Create: `cloud/app/sync/keys.py`
- Test: `cloud/tests/test_sync_keys.py`

**Interfaces:**
- Produces: `SYNC_CONFIG_KEYS: frozenset[str]` — nine keys from spec §6.1

- [ ] **Step 1: Test count and membership**

```python
from app.sync.keys import SYNC_CONFIG_KEYS
def test_whitelist_matches_spec():
    assert len(SYNC_CONFIG_KEYS) == 9
    assert "publishing_platforms.local" in SYNC_CONFIG_KEYS
```

- [ ] **Step 5: Commit**

---

### Task 14: Config sync router

**Files:**
- Create: `cloud/app/routers/config_sync.py`
- Test: `cloud/tests/test_config_sync.py`

**Interfaces:**
- `GET /sync/config/manifest`
- `GET /sync/config/{config_key}`
- `PUT /sync/config/{config_key}` body `{ content_yaml, content_hash, schema_version }`
- Validates `config_key in SYNC_CONFIG_KEYS`; checks `limits.config_sync_enabled` from entitlements service

- [ ] **Step 1: Failing test — unknown key 400**

```python
def test_put_unknown_key_400(auth_client):
    r = auth_client.put(
        "/sync/config/not_allowed.local",
        json={"content_yaml": "a: 1\n", "content_hash": "x", "schema_version": 1},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Test free plan 403**

- [ ] **Step 3: Test PUT stores sha256 hash**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cloud): config sync manifest and blob API"
```

---

### Task 15: Local sanitizer + reconcile (Data Plane) — cross-reference

**Not Cloud code** but required before end-to-end P4 gate. Implement per legacy plan **Task 15** (`services/cloud_sync/sanitize.py`, `reconcile.py`). Cloud phase P4 gate for **this** plan is Cloud API only; full P4 product gate adds legacy **Task 16** (Tauri `sync.rs`).

---

## Phase P5 — Desktop entitlements guard integration

**Depends on:** P3 `GET /entitlements` deployed or local `uvicorn`; desktop UserCenter token available.

**Phase gate:**

```bash
pytest tests/test_entitlements_guard.py -v
# Manual: expire entitlements.json → POST /api/generate-summary → 402
```

---

### Task 16: Entitlements cache + guard (reuse legacy Task 17)

**Files:**
- Create: `services/entitlements/cache.py`, `guard.py`, `errors.py`
- Test: `tests/test_entitlements_guard.py`

Follow legacy plan **Task 17** steps verbatim; ensure cache path uses `get_data_dir() / "cache" / "entitlements.json"` when `paths.py` exists.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(entitlements): local cache and entitlement guard"
```

---

### Task 17: Tauri — refresh entitlements from Cloud

**Files:**
- Create or modify: `desktop/src-tauri/src/cloud_entitlements.rs` (or `sync.rs` prelude)
- Modify: `desktop/src-tauri/src/main.rs` startup sequence

**Interfaces:**
- Consumes: UserCenter `access_token` from `auth/session.rs`
- Env: `AINEWS_CLOUD_API` (e.g. `http://localhost:8090`)
- Produces: writes `entitlements.json` before spawning Python

- [ ] **Step 1: On login success / app start (authenticated), `GET {AINEWS_CLOUD_API}/entitlements`**

- [ ] **Step 2: Write JSON to `%APPDATA%/AINews/cache/entitlements.json`**

- [ ] **Step 3: Manual: login → file exists with `plan_id`**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(desktop): fetch cloud entitlements after UserCenter login"
```

**Auth note:** Do **not** add Cloud login UI; token comes from UserCenter only (errata).

---

### Task 18: Route guards (reuse legacy Task 18)

**Files:**
- Modify: `api/routes/crawler_routes.py`, `api/routes/publishing_routes.py`
- Test: extend `tests/test_entitlements_guard.py` or `tests/test_entitlement_routes.py`

- [ ] `check_entitlement("ai_summary")` on summary endpoints
- [ ] `check_entitlement("publish_account")` on `qr-start`
- [ ] `EntitlementError` → HTTP **402** with `{"code":"entitlement_required","feature":"..."}`

---

### Task 19: Local status API + soft-limit UI (reuse legacy Task 19)

**Files:**
- Create: `api/routes/entitlements_routes.py` — `GET /api/entitlements/status` (reads cache only)
- Modify: `static/settings.html` + JS banner

---

## Spec coverage self-check (Cloud plan)

| Spec | Task |
|------|------|
| §5.1 no Cloud auth | Non-goals + errata reference |
| §5.2 schema | Task 3 |
| §5.3 JWT middleware | Tasks 4–7 |
| §5.3.3 `/me` | Task 8 |
| §5.3.4 subscription + entitlements | Tasks 9–10 |
| §5.3.5 sync | Tasks 13–14 |
| §5.5 env | Task 2, `.env.example` |
| §6 sync whitelist | Task 13–14 |
| §7.2 entitlements + extensions | Task 10 |
| Appendix B JWT tests | Tasks 5–6 |
| §7.3 guard | Tasks 16–18 |

**Gaps intentionally elsewhere:** P0–P2 desktop (legacy plan), P6 payments, sanitizer E2E (legacy Task 15–16).

---

## Execution order

```
P3 Task 1–12 (Cloud core)
    → P4 Task 13–14 (sync API) ∥ optional Task 15 legacy sanitizer
    → P5 Task 16–19 (guards + Tauri refresh)
```

Parallel: Desktop UserCenter auth (**done**); P0/P1 from legacy plan.

---

**Plan complete and saved to `docs/superpowers/plans/2026-09-17-ainews-cloud-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch one subagent per task, review between tasks.

**2. Inline Execution** — run `executing-plans` in one session with phase checkpoints (P3 → P4 → P5 gates).
