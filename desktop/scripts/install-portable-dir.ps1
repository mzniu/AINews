# Install dist\AINews_*_portable folder to a target directory (run elevated for Program Files).
param(
    [string]$AppVersion = "1.0.4",
    [string]$InstallDir = "$env:ProgramFiles\AINews"
)

$ErrorActionPreference = "Stop"
$Src = Resolve-Path (Join-Path $PSScriptRoot "..\dist\AINews_${AppVersion}_x64-portable")
if (-not (Test-Path (Join-Path $Src "ainews-desktop.exe"))) {
    throw "Portable build missing: $Src (run build-release-fast.ps1 first)"
}

& (Join-Path $PSScriptRoot "stop-ainews.ps1")

Write-Host "Installing from $Src"
Write-Host "           to $InstallDir"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
robocopy $Src $InstallDir /E /NFL /NDL /NJH /NJS /R:2 /W:2 | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed with exit code $LASTEXITCODE"
}

$pyRoot = Join-Path $InstallDir "bundle-resources\python"
if (Test-Path (Join-Path $pyRoot "pyvenv.cfg")) {
    & (Join-Path $PSScriptRoot "repair-installed-pyvenv.ps1") -PythonRoot $pyRoot
}

$launch = Join-Path $InstallDir "ainews-desktop.exe"
Write-Host "Install OK: $launch"
Start-Process -FilePath $launch
