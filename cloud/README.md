# AINews Cloud Control Plane

Production base URL: **https://ainews-api.xiaoniuliaoai.com**

## Local dev

```bash
cd cloud
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./ainews_cloud.db
export AINEWS_AUTH_JWT_SECRET=dev-secret
export PACKS_ROOT=../packs
python scripts/seed_industry_packs.py
PYTHONPATH=. uvicorn app.main:app --reload --port 8090
```

## Tests

```bash
cd cloud && PYTHONPATH=. pytest tests -q
```

## Docker PostgreSQL

```bash
docker compose up -d
export DATABASE_URL=postgresql://ainews:ainews@localhost:5433/ainews_cloud
alembic upgrade head  # when migrations land
python scripts/seed_industry_packs.py
```

## Industry APIs (Bearer JWT required)

- `GET /health`
- `GET /me`
- `PUT /me/active-industry` — `{"active_industry_id":"finance/macro"}`
- `GET /industry/taxonomy`
- `GET /industry-packs/{path}/manifest`
