# Rewrite bundled venv pyvenv.cfg home= to the install path (requires write access to install dir).
param(
    [Parameter(Mandatory = $true)]
    [string]$PythonRoot
)

$ErrorActionPreference = "Stop"
$PythonRoot = (Resolve-Path -LiteralPath $PythonRoot).Path
$cfgPath = Join-Path $PythonRoot "pyvenv.cfg"
if (-not (Test-Path $cfgPath)) {
    Write-Host "repair-installed-pyvenv: no pyvenv.cfg (skip)"
    exit 0
}

$interpreter = Join-Path $PythonRoot "python.exe"
if (-not (Test-Path $interpreter)) {
    throw "repair-installed-pyvenv: missing python.exe under $PythonRoot"
}

$lines = Get-Content -Path $cfgPath -Encoding UTF8
$version = "3.11.0"
$include = "false"
function Read-CfgValue([string]$Line) {
    if ($Line -match '^\s*\w[\w-]*\s*=\s*(.+)$') {
        return ($Matches[1] -replace '^(=\s*)+', '').Trim()
    }
    return $null
}
foreach ($line in $lines) {
    if ($line -match '^\s*version\s*=') { $version = Read-CfgValue $line }
    if ($line -match '^\s*include-system-site-packages\s*=') { $include = Read-CfgValue $line }
}
if (-not $version) { $version = "3.11.0" }
if (-not $include) { $include = "false" }

$newCfg = @(
    "home = $PythonRoot"
    "include-system-site-packages = $include"
    "version = $version"
) -join "`n"
$newCfg += "`n"

Set-Content -Path $cfgPath -Value $newCfg -Encoding UTF8 -NoNewline
Write-Host "repair-installed-pyvenv: home = $PythonRoot"
