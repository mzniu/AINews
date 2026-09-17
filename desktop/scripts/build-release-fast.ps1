# Fast release: refresh app bundle + rebuild Tauri/NSIS (reuse existing python/playwright).
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$TauriDir = Join-Path $PSScriptRoot "..\src-tauri"
$BundleRoot = Join-Path $TauriDir "bundle-resources"
$AppDst = Join-Path $BundleRoot "app"
$PythonExe = Join-Path $BundleRoot "python\Scripts\python.exe"
$PipExe = Join-Path $BundleRoot "python\Scripts\pip.exe"

Write-Host "==> AINews fast release build 1.0.3"
python (Join-Path $PSScriptRoot "generate-icons.py")
if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }
if (-not (Test-Path $PythonExe)) {
    throw "Bundled python not found. Run build-release.ps1 once first."
}

if (Test-Path $AppDst) {
    Remove-Item -Recurse -Force $AppDst
}
New-Item -ItemType Directory -Force -Path $AppDst | Out-Null

$ExcludeDirs = @(
    ".git", ".venv", "venv", "data", "desktop", "cloud", "node_modules",
    "third_party", "models", ".cache", "test_outputs", "__pycache__", ".pytest_cache",
    "tmp"
)

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

Get-ChildItem -Path $AppDst -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "==> Syncing bundled venv with requirements.txt..."
& $PipExe install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install requirements failed" }

Write-Host "==> Building Tauri NSIS installer..."
Push-Location $TauriDir
try {
    cargo build --release
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed" }
    cargo tauri bundle --bundles nsis
    if ($LASTEXITCODE -ne 0) { throw "cargo tauri bundle failed" }
} finally {
    Pop-Location
}

$Installer = Join-Path $TauriDir "target\release\bundle\nsis\AINews_1.0.3_x64-setup.exe"
$DistDir = Join-Path $PSScriptRoot "..\dist"
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
if (Test-Path $Installer) {
    Copy-Item $Installer (Join-Path $DistDir "AINews_1.0.3_x64-setup.exe") -Force
    Write-Host "==> Installer: $Installer"
    Write-Host "==> Copied to: $(Join-Path $DistDir 'AINews_1.0.3_x64-setup.exe')"
} else {
    throw "Installer not found: $Installer"
}
