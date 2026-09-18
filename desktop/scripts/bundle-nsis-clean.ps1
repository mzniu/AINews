# Clean NSIS temp state and build AINews NSIS installer (use after mmap / #12345 failures).
$ErrorActionPreference = "Stop"
$AppVersion = (Get-Content (Join-Path $PSScriptRoot "..\src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json).version
$TauriDir = Resolve-Path (Join-Path $PSScriptRoot "..\src-tauri")
$DistDir = Join-Path $PSScriptRoot "..\dist"
$NsisTmp = Join-Path $PSScriptRoot "..\.nsis-tmp"

Write-Host "==> AINews NSIS clean bundle v$AppVersion"

Write-Host "==> Stopping desktop app (if running)..."
& (Join-Path $PSScriptRoot "stop-ainews.ps1") -ErrorAction SilentlyContinue

Write-Host "==> Clearing NSIS temp under %TEMP%..."
Get-ChildItem $env:TEMP -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^(nsis|nst|makensis)' -or $_.Name -like '*nsis*'
} | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

if (Test-Path $NsisTmp) {
    Remove-Item -LiteralPath $NsisTmp -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $NsisTmp | Out-Null
$env:TEMP = $NsisTmp
$env:TMP = $NsisTmp
Write-Host "    TEMP=$NsisTmp"

$PythonRoot = Join-Path $TauriDir "bundle-resources\python"
$BundleRoot = Join-Path $TauriDir "bundle-resources"
if (Test-Path (Join-Path $PythonRoot "Scripts\python.exe")) {
    & (Join-Path $PSScriptRoot "relocate-bundled-python.ps1") -PythonRoot $PythonRoot
    & (Join-Path $PSScriptRoot "prune-bundled-payload.ps1") -BundleRoot $BundleRoot
    Write-Host "==> Pruning bundled python __pycache__ / .pyc..."
    Get-ChildItem -Path $PythonRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $PythonRoot -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

if (Test-Path (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) "NSIS\makensis.exe")) {
    & (Join-Path $PSScriptRoot "upgrade-tauri-nsis.ps1")
}
$tauriMakensis = Join-Path $env:LOCALAPPDATA "tauri\NSIS\makensis.exe"
if (-not (Test-Path $tauriMakensis)) {
    throw "Tauri NSIS cache missing. Run: cargo tauri bundle --bundles nsis (once) to bootstrap."
}
Write-Host "==> Tauri will use: $tauriMakensis"
& $tauriMakensis /VERSION

Push-Location $TauriDir
try {
    Write-Host "==> cargo build --release..."
    cargo build --release
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed" }

    Write-Host "==> cargo tauri bundle --bundles nsis..."
    cargo tauri bundle --bundles nsis
    if ($LASTEXITCODE -ne 0) { throw "cargo tauri bundle failed" }
} finally {
    Pop-Location
}

$Installer = Join-Path $TauriDir "target\release\bundle\nsis\AINews_${AppVersion}_x64-setup.exe"
if (Test-Path $Installer) {
    New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
    $DistInstaller = Join-Path $DistDir "AINews_${AppVersion}_x64-setup.exe"
    Copy-Item $Installer $DistInstaller -Force
    Write-Host "==> OK: $DistInstaller"
    Write-Host "    Size GB: $([math]::Round((Get-Item $DistInstaller).Length / 1GB, 2))"
    exit 0
}

Write-Warning "NSIS failed (bundle-resources likely >2GB uncompressed). Building 7z SFX setup.exe..."
& (Join-Path $PSScriptRoot "build-setup-sfx.ps1") -AppVersion $AppVersion -SkipPortableBuild
