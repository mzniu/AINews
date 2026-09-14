# AINews Desktop (Tauri 2)

Tauri shell for the AINews local Python backend.

## Prerequisites

- Rust stable
- `cargo install tauri-cli --version "^2.0.0"`
- Python 3.11+ with project dependencies installed

## Dev mode

```powershell
cd desktop
cargo tauri dev
```

Set `AINES_DEV_MODE=1` (default in dev) to skip cloud login.

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
