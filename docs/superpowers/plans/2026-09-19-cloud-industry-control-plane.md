# Cloud Industry Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the **multi-industry cloud slice** so desktop `sync-pack` returns `pack_source: cloud`, `PUT /me/active-industry` persists on the server, and taxonomy/manifest APIs match the existing Python client (`pack_client.py`, `cloud_profile.py`).

**Architecture:** `cloud/` FastAPI service with JWT (UserCenter HS256), SQLite/PG, pack releases seeded from repo `packs/`. Production API base: **`https://ainews-api.xiaoniuliaoai.com`** (desktop default `AINEWS_CLOUD_API_BASE`).

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2 · PostgreSQL 15 · PyYAML · pytest · python-jose

## Global Constraints

- No UserCenter auth routes on Cloud — Bearer JWT only.
- API paths: `GET /industry/taxonomy`, `GET /industry-packs/{path}/manifest`, `PUT /me/active-industry`, `GET /me`.
- Desktop env: `AINEWS_CLOUD_API_BASE` + `AINEWS_CLOUD_ACCESS_TOKEN`.

## Progress (2026-09-19)

- [x] `cloud/` scaffold: health, JWT, workspace lazy-create, industry manifest + active L2
- [x] `scripts/seed_industry_packs.py`
- [x] Desktop default `AINEWS_CLOUD_API_BASE=https://ainews-api.xiaoniuliaoai.com`
- [ ] Deploy to `ainews-api.xiaoniuliaoai.com` with PG + `AINEWS_AUTH_JWT_SECRET` matching UserCenter
- [ ] Alembic migrations for production PG
- [ ] CI job `pytest cloud/tests`

See also: [2026-09-17-ainews-cloud-implementation.md](./2026-09-17-ainews-cloud-implementation.md) for full P3–P5 entitlements/sync.
