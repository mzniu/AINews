# AINews Desktop (Tauri 2)

Tauri shell for the AINews local Python backend.

## Prerequisites

- Rust stable
- `cargo install tauri-cli --version "^2.0.0"`
- Python 3.11+ with project dependencies installed

## Dev mode

`cargo tauri dev` waits for `http://localhost:8088`. Start the Python backend first, or use the helper script:

```powershell
# from repo root
.\desktop\scripts\start-dev.ps1
```

Manual equivalent:

```powershell
# terminal 1 — repo root
$env:AINES_DEV_MODE = "1"
$env:PORT = "8088"
.\venv\Scripts\python.exe web_server.py

# terminal 2 — after /api/health is ok
cd desktop
$env:AINES_DEV_MODE = "1"
cargo tauri dev
```

`AINES_DEV_MODE=1` skips cloud login. Stop with `.\desktop\scripts\stop-ainews.ps1`.

## Build

```powershell
cd desktop
cargo tauri build
```

## Video performance recovery upgrade drill

Use an isolated directory (never writes the live AppData DB):

```powershell
python scripts/desktop_upgrade_drill.py `
  --source-db "$env:APPDATA\AINews\ainews.db" `
  --root tmp\desktop-upgrade-drill `
  --json-out tmp\desktop-upgrade-drill\report.json
```

Then follow the printed `go_live_order` (shadow deploy → dry-run rebuild → wechat → douyin → kuaishou).
