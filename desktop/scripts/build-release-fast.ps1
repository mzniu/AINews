# Fast release: refresh app bundle + rebuild Tauri/NSIS (reuse existing python/playwright).

$ErrorActionPreference = "Stop"

$AppVersion = "1.0.13"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

$TauriDir = Join-Path $PSScriptRoot "..\src-tauri"

$BundleRoot = Join-Path $TauriDir "bundle-resources"

$AppDst = Join-Path $BundleRoot "app"

$PythonExe = Join-Path $BundleRoot "python\Scripts\python.exe"

$PipExe = Join-Path $BundleRoot "python\Scripts\pip.exe"



Write-Host "==> AINews fast release build $AppVersion"

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



Write-Host "==> Syncing bundled venv (slim desktop bundle, no torch/LaMa)..."

& $PipExe install -r (Join-Path $RepoRoot "requirements-desktop-bundle.txt")

if ($LASTEXITCODE -ne 0) { throw "pip install requirements failed" }

cmd /c "`"$PipExe`" uninstall -y simple-lama-inpainting torch torchvision >nul 2>nul"

Copy-Item (Join-Path $RepoRoot "requirements-desktop-extras.txt") (Join-Path $AppDst "requirements-desktop-extras.txt") -Force

$PlaywrightBrowsers = Join-Path $BundleRoot "playwright-browsers"

if (Test-Path $PlaywrightBrowsers) {

    Remove-Item -Recurse -Force $PlaywrightBrowsers

    Write-Host "==> Removed bundled playwright-browsers (first-run download)"

}



$PythonRoot = Split-Path (Split-Path $PythonExe -Parent) -Parent

& (Join-Path $PSScriptRoot "relocate-bundled-python.ps1") -PythonRoot $PythonRoot

Write-Host "==> Pruning bundled python __pycache__ / .pyc (smaller NSIS script)..."
Get-ChildItem -Path $PythonRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $PythonRoot -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

& (Join-Path $PSScriptRoot "prune-bundled-payload.ps1") -BundleRoot $BundleRoot

Write-Host "==> Building Tauri (release)..."

Push-Location $TauriDir

try {

    cargo build --release

    if ($LASTEXITCODE -ne 0) { throw "cargo build failed" }

    Write-Host "==> NSIS installer..."

    cargo tauri bundle --bundles nsis

    $nsisOk = ($LASTEXITCODE -eq 0)

} finally {

    Pop-Location

}



$DistDir = Join-Path $PSScriptRoot "..\dist"

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$Installer = Join-Path $TauriDir "target\release\bundle\nsis\AINews_${AppVersion}_x64-setup.exe"

$DistInstaller = Join-Path $DistDir "AINews_${AppVersion}_x64-setup.exe"



if ($nsisOk -and (Test-Path $Installer)) {

    Copy-Item $Installer $DistInstaller -Force

    Write-Host "==> Installer: $Installer"

    Write-Host "==> Copied to: $DistInstaller"

} else {

    Write-Warning "NSIS bundle failed (payload >2GB uncompressed); portable zip + 7z SFX setup..."

    & (Join-Path $PSScriptRoot "package-portable.ps1") -AppVersion $AppVersion -SkipCargoBuild

    & (Join-Path $PSScriptRoot "build-setup-sfx.ps1") -AppVersion $AppVersion -SkipPortableBuild

}


