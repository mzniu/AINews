# Sync Tauri-bundled NSIS with system NSIS 3.12 (Tauri always uses %LOCALAPPDATA%\tauri\NSIS on Windows).
$ErrorActionPreference = "Stop"
$tauriNsis = Join-Path $env:LOCALAPPDATA "tauri\NSIS"
$sysNsis = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) "NSIS"
$utilDll = Join-Path $tauriNsis "Plugins\x86-unicode\additional\nsis_tauri_utils.dll"

if (-not (Test-Path (Join-Path $sysNsis "makensis.exe"))) {
    throw "System NSIS not found at $sysNsis. Run: winget install NSIS.NSIS"
}

if (-not (Test-Path $tauriNsis)) {
    throw "Tauri NSIS cache missing: $tauriNsis (run cargo tauri bundle once)"
}

$utilBackup = Join-Path $env:TEMP "nsis_tauri_utils.dll.bak"
if (Test-Path $utilDll) {
    Copy-Item $utilDll $utilBackup -Force
    Write-Host "Backed up nsis_tauri_utils.dll"
}

Write-Host "Upgrading $tauriNsis from $sysNsis ..."
robocopy $sysNsis $tauriNsis /E /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with $LASTEXITCODE" }

if (Test-Path $utilBackup) {
    $utilDir = Split-Path $utilDll -Parent
    New-Item -ItemType Directory -Force -Path $utilDir | Out-Null
    Copy-Item $utilBackup $utilDll -Force
    Write-Host "Restored nsis_tauri_utils.dll"
}

& (Join-Path $tauriNsis "makensis.exe") /VERSION
Write-Host "Tauri NSIS cache upgraded."
