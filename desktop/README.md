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

Full installer (creates bundled venv + relocates Python for other PCs):

```powershell
.\desktop\scripts\build-release.ps1
```

Incremental installer (reuses existing `bundle-resources/python`, still runs relocate):

```powershell
.\desktop\scripts\build-release-fast.ps1
```

`relocate-bundled-python.ps1` copies runtime + `Lib`/`DLLs` into the bundled venv and sets `pyvenv.cfg` `home` to that folder. At runtime the desktop app always starts backend with `bundle-resources/python/python.exe` and `PYTHONHOME` pointing at the same directory (so other machines never depend on the builder’s Python path).

**First-run downloads:** Desktop bundles use `requirements-desktop-bundle.txt` (no torch/LaMa). On first launch, the app downloads ML extras (`pip install --user` from `requirements-desktop-extras.txt`) and Playwright Chromium to `%APPDATA%\\AINews\\playwright-browsers`. Progress is shown on the login startup overlay.

**NSIS note:** Standard makensis cannot pack more than **2GB uncompressed** payload. With bundled Python + Playwright + torch, `bundle-resources` is ~3.5GB+, so `cargo tauri bundle` may fail with `mmap … out of range`. Use `build-setup-sfx.ps1` (7-Zip SFX `setup.exe`) or `package-portable.ps1` (zip). Scripts: `bundle-nsis-clean.ps1`, `upgrade-tauri-nsis.ps1`.

## Video performance recovery upgrade drill

Use an isolated directory (never writes the live AppData DB):

```powershell
python scripts/desktop_upgrade_drill.py `
  --source-db "$env:APPDATA\AINews\ainews.db" `
  --root tmp\desktop-upgrade-drill `
  --json-out tmp\desktop-upgrade-drill\report.json
```

Then follow the printed `go_live_order` (shadow deploy → dry-run rebuild → wechat → douyin → kuaishou).
