# Portable launcher for P0 gate: stores all user data under %APPDATA%\AINews
$DataDir = Join-Path $env:APPDATA "AINews"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$env:AINEWS_DATA_DIR = $DataDir
$env:PORT = "8088"
Write-Host "AINEWS_DATA_DIR=$DataDir"
Set-Location $PSScriptRoot\..
python web_server.py
