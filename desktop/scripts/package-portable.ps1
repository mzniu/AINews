# Portable folder + zip when NSIS fails (full install: unzip and run ainews-desktop.exe).

param(

    [string]$AppVersion = "1.0.4",

    [switch]$SkipCargoBuild

)



$ErrorActionPreference = "Stop"

$TauriDir = Join-Path $PSScriptRoot "..\src-tauri"

$BundleRoot = Join-Path $TauriDir "bundle-resources"

$PythonRoot = Join-Path $BundleRoot "python"

$DistDir = Join-Path $PSScriptRoot "..\dist"

$OutName = "AINews_${AppVersion}_x64-portable"

$Stage = Join-Path $DistDir $OutName



if (-not (Test-Path (Join-Path $PythonRoot "Scripts\python.exe"))) {

    throw "Bundled python missing. Run build-release.ps1 once first."

}



& (Join-Path $PSScriptRoot "relocate-bundled-python.ps1") -PythonRoot $PythonRoot



if (-not $SkipCargoBuild) {

    Push-Location $TauriDir

    try {

        cargo build --release

        if ($LASTEXITCODE -ne 0) { throw "cargo build --release failed" }

    } finally {

        Pop-Location

    }

}



$Exe = Join-Path $TauriDir "target\release\ainews-desktop.exe"

if (-not (Test-Path $Exe)) {

    throw "Missing $Exe"

}



if (Test-Path $Stage) {

    Remove-Item -Recurse -Force $Stage

}

New-Item -ItemType Directory -Force -Path $Stage | Out-Null

Copy-Item $Exe (Join-Path $Stage "ainews-desktop.exe") -Force

Copy-Item -Path $BundleRoot -Destination (Join-Path $Stage "bundle-resources") -Recurse -Force



$ZipPath = Join-Path $DistDir "$OutName.zip"

if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

Push-Location $DistDir
try {
    tar.exe -a -c -f $ZipPath $OutName
    if ($LASTEXITCODE -ne 0) { throw "tar failed to create $ZipPath" }
} finally {
    Pop-Location
}



Write-Host "==> Portable folder: $Stage"

Write-Host "==> Zip: $ZipPath"

Write-Host "Install: unzip to e.g. %LOCALAPPDATA%\AINews and run ainews-desktop.exe"


