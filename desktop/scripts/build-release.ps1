# AINews release build: stage Python app + venv, then cargo tauri build (NSIS installer).
param(
    [switch]$SkipPython,
    [switch]$SkipPlaywright
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$TauriDir = Join-Path $PSScriptRoot "..\src-tauri"
$BundleRoot = Join-Path $TauriDir "bundle-resources"
$AppDst = Join-Path $BundleRoot "app"
$PythonDst = Join-Path $BundleRoot "python"
$PlaywrightDst = Join-Path $BundleRoot "playwright-browsers"

Write-Host "==> AINews release build 1.0.5"
Write-Host "    Repo: $RepoRoot"

if (Test-Path $BundleRoot) {
    Remove-Item -Recurse -Force $BundleRoot
}
New-Item -ItemType Directory -Force -Path $AppDst | Out-Null

$ExcludeDirs = @(
    ".git", ".venv", "venv", "data", "desktop", "cloud", "node_modules",
    "third_party", "models", ".cache", "test_outputs", "__pycache__", ".pytest_cache",
    "tmp"
)
$ExcludeFiles = @("*.pyc", "*.pyo", ".env")

Write-Host "==> Copying application files..."
Get-ChildItem -Path $RepoRoot -Force | ForEach-Object {
    $name = $_.Name
    if ($ExcludeDirs -contains $name) { return }
    if ($name -like ".*" -and $name -ne ".env.example") { return }
    $dest = Join-Path $AppDst $name
    if ($_.PSIsContainer) {
        Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
    } else {
        Copy-Item -Path $_.FullName -Destination $dest -Force
    }
}

# Prune nested junk from copied tree
Get-ChildItem -Path $AppDst -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $AppDst -Recurse -Directory -Filter ".pytest_cache" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

if (-not $SkipPython) {
    Write-Host "==> Creating bundled Python venv (this may take several minutes)..."
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "python not found on PATH; install Python 3.11+ or pass -SkipPython"
    }
    python -m venv $PythonDst
    $pip = Join-Path $PythonDst "Scripts\pip.exe"
    $python = Join-Path $PythonDst "Scripts\python.exe"
    & $pip install --upgrade pip wheel
    & $pip install -r (Join-Path $RepoRoot "requirements-desktop-bundle.txt")
    & $pip uninstall -y simple-lama-inpainting torch torchvision 2>$null | Out-Null
    Copy-Item (Join-Path $RepoRoot "requirements-desktop-extras.txt") (Join-Path $AppDst "requirements-desktop-extras.txt") -Force
    if (Test-Path $PlaywrightDst) {
        Remove-Item -Recurse -Force $PlaywrightDst
        Write-Host "==> Skipped bundling Playwright browsers (first-run download)"
    }
    & (Join-Path $PSScriptRoot "relocate-bundled-python.ps1") -PythonRoot $PythonDst
    & (Join-Path $PSScriptRoot "prune-bundled-payload.ps1") -BundleRoot $BundleRoot
} else {
    Write-Host "==> Skipping Python bundle (-SkipPython)"
}

Write-Host "==> Building Tauri NSIS installer..."
Push-Location $TauriDir
try {
    cargo tauri build
} finally {
    Pop-Location
}

$BundleDir = Join-Path $TauriDir "target\release\bundle\nsis"
if (Test-Path $BundleDir) {
    Write-Host ""
    Write-Host "==> Build complete. Installers:"
    Get-ChildItem $BundleDir -Filter "*.exe" | ForEach-Object {
        Write-Host "    $($_.FullName)"
        Write-Host "    Silent install: $($_.Name) /S"
    }
} else {
    Write-Host "==> Build finished; check target\release\bundle for outputs."
}
