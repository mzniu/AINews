# Start AINews desktop in Tauri dev mode.
# cargo tauri dev waits for http://localhost:8088, so this script
# brings up the Python backend first, then the desktop shell.
param(
    [int]$Port = 8088
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$DesktopDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$HealthUrl = "http://127.0.0.1:$Port/api/health"

function Test-Backend {
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Resolve-Python {
    $venvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }
    $dotVenv = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $dotVenv) { return $dotVenv }
    return "python"
}

Get-Process ainews-desktop -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stopping existing ainews-desktop pid $($_.Id)"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Backend)) {
    $python = Resolve-Python
    Write-Host "Starting Python backend: $python web_server.py (PORT=$Port)"
    $env:AINES_DEV_MODE = "1"
    $env:PORT = "$Port"
    Start-Process -FilePath $python -ArgumentList "web_server.py" -WorkingDirectory $RepoRoot -WindowStyle Normal
    $deadline = (Get-Date).AddSeconds(40)
    do {
        Start-Sleep -Seconds 1
        if (Test-Backend) { break }
    } while ((Get-Date) -lt $deadline)
    if (-not (Test-Backend)) {
        throw "Backend did not become healthy at $HealthUrl"
    }
    Write-Host "Backend ready at $HealthUrl"
} else {
    Write-Host "Backend already running at $HealthUrl"
}

Write-Host "Starting cargo tauri dev (AINES_DEV_MODE=1)..."
$env:AINES_DEV_MODE = "1"
Set-Location $DesktopDir
cargo tauri dev
