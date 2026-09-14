# Import dev environment data into the desktop install data dir (%APPDATA%\AINews).
param(
    [string]$DevRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$TargetDataDir = (Join-Path $env:APPDATA "AINews"),
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"

$DevDataDir = Join-Path $DevRoot "data"
$DevConfigDir = Join-Path $DevRoot "config"
$DevEnvFile = Join-Path $DevRoot ".env"
$TargetConfigDir = Join-Path $TargetDataDir "config"

if (-not (Test-Path $DevDataDir)) {
    throw "Dev data dir not found: $DevDataDir"
}

Write-Host "==> Import dev data to desktop install"
Write-Host "    From: $DevDataDir"
Write-Host "    To:   $TargetDataDir"
Write-Host ""

& (Join-Path $PSScriptRoot "stop-ainews.ps1")

if ((Test-Path $TargetDataDir) -and -not $SkipBackup) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = "${TargetDataDir}.backup-$stamp"
    Write-Host "==> Backing up existing install data to:"
    Write-Host "    $backup"
    Move-Item -Path $TargetDataDir -Destination $backup
}

New-Item -ItemType Directory -Force -Path $TargetDataDir, $TargetConfigDir | Out-Null

Write-Host "==> Copying data (this may take several minutes)..."
$robocopyArgs = @(
    $DevDataDir,
    $TargetDataDir,
    "/E",
    "/R:2",
    "/W:2",
    "/NFL",
    "/NDL",
    "/NP",
    "/XD", "__pycache__", ".pytest_cache"
)
$rc = (Start-Process -FilePath "robocopy.exe" -ArgumentList $robocopyArgs -Wait -PassThru).ExitCode
if ($rc -ge 8) {
    throw "robocopy failed with exit code $rc"
}

Write-Host "==> Merging local config overrides..."
$localConfigs = @()
if (Test-Path $DevConfigDir) {
    $localConfigs += Get-ChildItem $DevConfigDir -Filter "*.local.yaml" -File -ErrorAction SilentlyContinue
}
$dataConfigDir = Join-Path $DevDataDir "config"
if (Test-Path $dataConfigDir) {
    $localConfigs += Get-ChildItem $dataConfigDir -Filter "*.local.yaml" -File -ErrorAction SilentlyContinue
}
foreach ($file in $localConfigs) {
    $dest = Join-Path $TargetConfigDir $file.Name
    Copy-Item $file.FullName $dest -Force
    Write-Host "    $($file.Name)"
}

if (Test-Path $DevEnvFile) {
    Copy-Item $DevEnvFile (Join-Path $TargetDataDir ".env") -Force
    Write-Host "==> Copied .env -> $(Join-Path $TargetDataDir '.env')"
} else {
    Write-Host "==> No .env found at $DevEnvFile (skipped)"
}

$sizeMb = [math]::Round(
    ((Get-ChildItem $TargetDataDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB),
    1
)
Write-Host ""
Write-Host "==> Import complete ($sizeMb MB)"
Write-Host "    Launch: C:\Program Files\AINews\ainews-desktop.exe"
Write-Host "    Data:   $TargetDataDir"
