# Continuous Integration (CI)

AINews uses [GitHub Actions](https://docs.github.com/en/actions) to run automated checks on every push and pull request.

Workflow file: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

## What runs

| Job | Purpose | Typical duration |
|-----|---------|------------------|
| **Python tests** | Install Python deps, Playwright Chromium, run `pytest tests/` | ~5–8 min |
| **Remotion** | `npm ci`, TypeScript typecheck, Remotion bundle smoke test | ~2–3 min |

Jobs run in parallel on `ubuntu-latest`.

## Triggers

- **Push** to any branch
- **Pull request** targeting any branch

Outdated runs on the same branch are cancelled automatically (`concurrency`).

## Local parity

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest pytest-cov httpx
python -m playwright install chromium
pytest tests/ -v
```

`pytest.ini` sets `testpaths = tests` and `pythonpath = .` so you can run pytest from the repo root without extra flags.

### Remotion

```bash
cd remotion
npm ci
npm run typecheck
npm run build
```

`npm run build` runs `remotion bundle` — it validates composition wiring without rendering a full MP4.

## Secrets and environment variables

**No GitHub secrets are required** for the current CI workflow. Tests use temporary SQLite databases and mocks; they do not call DeepSeek or production publishing APIs.

Optional repository variables (not configured today):

| Variable | When needed |
|----------|-------------|
| `DEEPSEEK_API_KEY` | Only if you add integration tests that call the live API |
| `INGESTION_DATABASE_URL` | Overridden per-test; not needed in CI |

## Deployment (CD)

There is **no CD job** in this workflow. The repo has no checked-in Docker/deploy target or production hook. Desktop/Tauri and publishing flows are released manually (see `desktop/README.md`).

To add CD later, extend `.github/workflows/ci.yml` or add a separate workflow (for example `deploy.yml`) triggered on `release` or `workflow_dispatch`, and document required secrets there.

## Extending CI

- **Linting**: add `ruff` / `eslint` steps once the project adopts them consistently.
- **Coverage**: append `--cov=src --cov=services` to the pytest step and upload with `codecov/codecov-action` if you want PR coverage reports.
- **Path filters**: use `paths` / `paths-ignore` on the workflow `on` block to skip Remotion when only Python changes (and vice versa).
- **Heavier renders**: avoid full `remotion render` in CI; use bundle smoke tests unless you provision ffmpeg + longer timeouts.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Playwright browser missing | Ensure `python -m playwright install chromium` ran (CI does this automatically). |
| Import errors in tests | Run from repo root; `PYTHONPATH=.` or use `pytest.ini` defaults. |
| Remotion bundle fails | Run `npm ci` in `remotion/`; check Node 20+. |
| Cairo / SVG errors in Python | Install `libcairo2-dev` (CI installs this for `cairosvg`). |
