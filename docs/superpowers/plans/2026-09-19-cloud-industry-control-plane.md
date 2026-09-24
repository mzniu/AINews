# Cloud Industry Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the **multi-industry cloud slice** so desktop `sync-pack` returns `pack_source: cloud`, `PUT /me/active-industry` persists on the server, and taxonomy/manifest APIs match the existing Python client (`pack_client.py`, `cloud_profile.py`).

**Architecture:** Extend the `cloud/` FastAPI service from [2026-09-17-ainews-cloud-implementation.md](./2026-09-17-ainews-cloud-implementation.md) (P3 JWT + workspace) with read-mostly **pack catalog** tables seeded from repo `packs/`, plus **workspace profile** column(s) for `active_industry_id`. Desktop continues to use bundled fallback when cloud is down; cloud is source of truth when reachable.

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 15 · PyYAML · pytest · httpx · UserCenter JWT (same as P3)

## Global Constraints

- **No UserCenter auth on Cloud** — validate Bearer JWT only; identity from `usercenter_user_id` claim ([errata](../specs/2026-09-17-usercenter-cloud-integration-errata.md)).
- **API shapes** must match [multi-industry vertical design §5](../specs/2026-09-17-multi-industry-vertical-design.md) and desktop stubs:
  - `GET /industry/taxonomy`
  - `GET /industry-packs/{industry_path}/manifest` → includes `content_yaml`, `pack_version`, `l1_defaults_key`, optional `l1_defaults_yaml` in body for client `persist_pack_manifest`
  - `PUT /me/active-industry` ← JSON `{"active_industry_id":"finance/macro"}`
- **M0 billing:** no hard gate on pack download; `GET /subscription` may expose `premium_paths` later.
- **Desktop env:** `AINEWS_CLOUD_API_BASE` (Control Plane URL, not UserCenter login URL) + `AINEWS_CLOUD_ACCESS_TOKEN` (already injected from Tauri on backend spawn).

## Prerequisites

- [ ] P3 **Task 1–6** complete: `cloud/` health, DB, JWT deps, `GET /me`, personal workspace lazy-create ([parent plan](./2026-09-17-ainews-cloud-implementation.md)).
- [ ] Desktop **#19 merged** (`sync-pack` no longer 500 on reload); local `pack_source` field in API response.

## File Map (additions under `cloud/`)

| Path | Responsibility |
|------|----------------|
| `cloud/app/models/industry.py` | `IndustryPackRelease`, optional `IndustryTaxonomySnapshot` |
| `cloud/app/models/workspace.py` | extend workspace: `active_industry_id`, `industry_selected_at` |
| `cloud/alembic/versions/002_industry_packs.py` | schema + indexes |
| `cloud/app/services/industry_catalog.py` | Load/serve manifest from DB; validate `industry_id` regex |
| `cloud/app/services/industry_profile.py` | `set_active_industry(workspace, path)` |
| `cloud/app/routers/industry.py` | `GET /industry/taxonomy`, `GET /industry-packs/{path}/manifest` |
| `cloud/app/routers/me.py` | add `PUT /me/active-industry` (or `me_industry.py`) |
| `cloud/scripts/seed_industry_packs.py` | Import `packs/` from monorepo into PG |
| `cloud/tests/test_industry_manifest.py` | Manifest contract vs desktop `fetch_pack_manifest` |
| `cloud/tests/test_active_industry.py` | PUT + GET `/me` reflects profile |

**Desktop / monorepo (P5b — after cloud deployable):**

| Path | Responsibility |
|------|----------------|
| `desktop/src-tauri/src/backend.rs` | `env("AINEWS_CLOUD_API_BASE", control_plane_url)` |
| `desktop/src-tauri/src/auth/config.rs` | `control_plane_base_url()` default or env `AINEWS_CLOUD_API_BASE` |
| `docs/superpowers/specs/...` | link this plan |

---

## Phase CI — Cloud industry APIs (depends on P3)

**Phase gate:** With valid JWT and seeded DB: `GET /industry-packs/tech/ai/manifest` returns `content_yaml`; `PUT /me/active-industry` updates row; desktop integration test (manual): `sync-pack` → `pack_source: cloud`.

```bash
cd cloud && alembic upgrade head && python scripts/seed_industry_packs.py
pytest cloud/tests/test_industry_manifest.py cloud/tests/test_active_industry.py -v
```

---

### Task 1: DB schema for packs + workspace active L2

**Files:** `cloud/app/models/industry.py`, migration `002_industry_packs.py`, extend workspace model.

- [ ] **Step 1:** Write migration test or alembic upgrade smoke asserting tables `industry_pack_releases`, workspace columns exist.
- [ ] **Step 2:** Model `IndustryPackRelease(path PK, pack_version, content_yaml, content_hash, l1_defaults_yaml nullable, updated_at)`.
- [ ] **Step 3:** Add `active_industry_id` (nullable string), `industry_selected_at` (timestamptz) on `workspaces`.
- [ ] **Step 4:** `alembic upgrade head` in CI.
- [ ] **Step 5:** Commit `feat(cloud): industry pack releases and workspace active L2 columns`.

---

### Task 2: Seed packs from monorepo

**Files:** `cloud/scripts/seed_industry_packs.py`

- [ ] **Step 1:** Read `packs/taxonomy.yaml` + each `packs/{l1}/{l2}.yaml` + `packs/{l1}/_defaults.yaml`.
- [ ] **Step 2:** Upsert into `industry_pack_releases`; compute `content_hash` = `sha256:` hex of L2 file (match desktop `manifest_hash_for_pack`).
- [ ] **Step 3:** Idempotent re-run (CI + dev).
- [ ] **Step 4:** Commit `chore(cloud): seed industry packs from bundled yaml`.

---

### Task 3: `GET /industry/taxonomy`

**Files:** `cloud/app/routers/industry.py`, `cloud/app/services/industry_catalog.py`

- [ ] **Step 1:** Failing test: response shape matches desktop `packs/taxonomy.yaml` (6 L2 paths).
- [ ] **Step 2:** Implement — **M0:** serve from seeded snapshot or static file; auth optional (recommend **Bearer required** for parity with paid product).
- [ ] **Step 3:** Commit `feat(cloud): GET /industry/taxonomy`.

---

### Task 4: `GET /industry-packs/{path}/manifest`

**Files:** same router + catalog service

- [ ] **Step 1:** Test 404 for unknown path; test 200 for `tech/ai` with non-empty `content_yaml`.
- [ ] **Step 2:** Include `l1_defaults_yaml` in JSON when `_defaults.yaml` exists (desktop `persist_pack_manifest` uses it).
- [ ] **Step 3:** Align field names with `services/industry/pack_client.py` (`path`, `pack_version`, `content_hash`, `l1_defaults_key`, `updated_at`).
- [ ] **Step 4:** Commit `feat(cloud): industry pack manifest API`.

---

### Task 5: `PUT /me/active-industry`

**Files:** `cloud/app/routers/me.py`, `industry_profile.py`

- [ ] **Step 1:** Test rejects invalid `industry_id` format; rejects unknown L2 not in taxonomy.
- [ ] **Step 2:** Test updates workspace row; returns `{ active_industry_id, pack_version }` from latest release.
- [ ] **Step 3:** Wire `activate_industry_l2` on desktop to treat `synced: true` from cloud (already calls `put_cloud_active_industry`).
- [ ] **Step 4:** Commit `feat(cloud): PUT /me/active-industry`.

---

### Task 6: Extend `GET /me` with industry fields

- [ ] **Step 1:** Test `active_industry_id` null for new workspace; set after PUT.
- [ ] **Step 2:** Add `industry_selected_at` to JSON per spec §5.2.
- [ ] **Step 3:** Commit `feat(cloud): expose active industry on GET /me`.

---

## Phase CD — Desktop wiring

**Phase gate:** Logged-in desktop user: Settings → 同步行业包 shows `pack_source: cloud` against staging Control Plane.

### Task 7: Inject `AINEWS_CLOUD_API_BASE` in Tauri

**Files:** `desktop/src-tauri/src/backend.rs`, `auth/config.rs`

- [ ] **Step 1:** Add env `AINEWS_CLOUD_API_BASE` (default e.g. `https://api.jiamenkou.online` or staging URL — **must not** default to UserCenter `/v1/auth` host unless same service).
- [ ] **Step 2:** Pass to `spawn_backend` alongside existing `AINEWS_CLOUD_ACCESS_TOKEN`.
- [ ] **Step 3:** Document in `desktop/README.md`.
- [ ] **Step 4:** Commit `feat(desktop): pass cloud control plane base URL to Python`.

---

### Task 8: Contract test against cloud (optional CI job)

- [ ] **Step 1:** `tests/test_industry_pack_client.py` — httpx mock or recorded fixture from cloud OpenAPI.
- [ ] **Step 2:** Mark `@pytest.mark.integration` for staging URL.

---

## Phase CO — Ops & content workflow

### Task 9: Pack publish runbook

- [ ] **Step 1:** Document: edit `packs/` in monorepo → run `seed_industry_packs.py` on deploy → bump `pack_version` in yaml.
- [ ] **Step 2:** Future: admin API `POST /admin/industry-packs` (out of M0 scope).

---

## Out of scope (later)

- `GET /industry-packs/{path}/bundle` (zip)
- Cross-device conflict resolution for `active_industry_id`
- Entitlement hard-block on `premium_paths`
- Hot-radar TopHub proxy (`/api/ingestion/hot-radar/nodes` — **not** in desktop API today; fix client paths separately)

---

## Suggested execution order

1. Finish **P3** cloud scaffold + JWT (if not already on branch).
2. **CI Tasks 1–6** (industry APIs) — can demo with `curl` + desktop `AINEWS_CLOUD_API_BASE`.
3. **CD Task 7** — removes manual env for end users.
4. Staging deploy + manual onboarding → sync-pack smoke.

## References

- Desktop client: `services/industry/pack_client.py`, `services/industry/cloud_profile.py`
- Spec: `docs/superpowers/specs/2026-09-17-multi-industry-vertical-design.md` §5
- Parent cloud plan: `docs/superpowers/plans/2026-09-17-ainews-cloud-implementation.md`
- Recent fix: PR #19 — `sync-pack` reload / SQLite
