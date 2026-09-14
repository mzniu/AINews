# One-shot elevated install helper (accept UAC prompt when it appears).
$InstallerPath = "D:\git\AINews\desktop\dist\AINews_1.0.2_x64-setup.exe"
$InstallDir = "$env:ProgramFiles\AINews"

if (-not (Test-Path $InstallerPath)) {
    throw "Installer not found: $InstallerPath"
}

& (Join-Path $PSScriptRoot "stop-ainews.ps1")

Write-Host "Installing AINews to $InstallDir ..."
$proc = Start-Process -FilePath $InstallerPath -ArgumentList "/S", "/D=$InstallDir" -Verb RunAs -Wait -PassThru
if ($null -eq $proc) {
    throw "Installer was not started (UAC cancelled or elevation denied)."
}
if ($proc.ExitCode -ne 0) {
    throw "Installer exited with code $($proc.ExitCode)"
}

$launchExe = Join-Path $InstallDir "ainews-desktop.exe"
if (-not (Test-Path $launchExe)) {
    throw "Install finished but executable not found: $launchExe"
}

Write-Host "Install OK. Launching $launchExe"
Start-Process -FilePath $launchExe
