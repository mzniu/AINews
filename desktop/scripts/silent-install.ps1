# Silent install AINews NSIS installer (stops running instances first).
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [string]$InstallDir = "$env:ProgramFiles\AINews"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $InstallerPath)) {
    throw "Installer not found: $InstallerPath"
}

& (Join-Path $PSScriptRoot "stop-ainews.ps1")

Write-Host "Silent installing AINews to $InstallDir (requires admin) ..."
$proc = Start-Process -FilePath $InstallerPath -ArgumentList "/S", "/D=$InstallDir" -Verb RunAs -Wait -PassThru
if ($null -eq $proc) {
    throw "Installer was not started (UAC cancelled or elevation denied)."
}
if ($proc.ExitCode -ne 0) {
    throw "Installer exited with code $($proc.ExitCode)"
}

$launchExe = Join-Path $InstallDir "ainews-desktop.exe"
if (-not (Test-Path $launchExe)) {
    $launchExe = Join-Path $InstallDir "AINews.exe"
}
if (-not (Test-Path $launchExe)) {
    throw "Install finished but executable not found under $InstallDir"
}
Write-Host "Done. Launch: $launchExe"
