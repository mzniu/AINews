# NSIS fallback: 7-Zip self-extracting installer (when makensis mmap fails on large payloads).
param(
    [string]$AppVersion = "1.0.4",
    [switch]$SkipPortableBuild
)

$ErrorActionPreference = "Stop"
$DistDir = Join-Path $PSScriptRoot "..\dist"
$Folder = Join-Path $DistDir "AINews_${AppVersion}_x64-portable"
$OutExe = Join-Path $DistDir "AINews_${AppVersion}_x64-setup.exe"

if (-not $SkipPortableBuild -or -not (Test-Path (Join-Path $Folder "ainews-desktop.exe"))) {
    & (Join-Path $PSScriptRoot "package-portable.ps1") -AppVersion $AppVersion -SkipCargoBuild
}

$7zCandidates = @(
    (Join-Path $env:ProgramFiles "7-Zip\7z.exe"),
    (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) "7-Zip\7z.exe")
)
$7z = $7zCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $7z) {
    Write-Warning "7-Zip not found. Use portable zip: $(Join-Path $DistDir "AINews_${AppVersion}_x64-portable.zip")"
    exit 0
}

$config = @"
;!@Install@!UTF-8!
Title="AINews $AppVersion"
BeginPrompt="Install AINews $AppVersion to the selected folder?"
RunProgram="ainews-desktop.exe"
;!@InstallEnd@!
"@
$cfgPath = Join-Path $env:TEMP "ainews-sfx-config.txt"
Set-Content -Path $cfgPath -Value $config -Encoding UTF8

& $7z a -t7z -mx=5 (Join-Path $DistDir "_ainews_payload.7z") $Folder
if ($LASTEXITCODE -ne 0) { throw "7z archive failed" }

$sfxModule = Join-Path (Split-Path $7z -Parent) "7z.sfx"
if (-not (Test-Path $sfxModule)) { throw "Missing 7z.sfx" }

if (Test-Path $OutExe) { Remove-Item -Force $OutExe }
cmd /c "copy /b `"$sfxModule`" + `"$cfgPath`" + `"$(Join-Path $DistDir '_ainews_payload.7z')`" `"$OutExe`""
if (-not (Test-Path $OutExe)) { throw "SFX setup.exe not created" }

Write-Host "==> SFX installer: $OutExe"
