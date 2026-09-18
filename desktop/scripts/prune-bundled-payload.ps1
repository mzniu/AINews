# Shrink bundle-resources for NSIS (<2GB uncompressed) and remove known junk.
param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot
)

$ErrorActionPreference = "Stop"
$PythonRoot = Join-Path $BundleRoot "python"
$AppRoot = Join-Path $BundleRoot "app"

$nestedSite = Join-Path $PythonRoot "Lib\site-packages\site-packages"
if (Test-Path $nestedSite) {
    Write-Host "==> Removing mistaken nested site-packages: $nestedSite"
    Remove-Item -LiteralPath $nestedSite -Recurse -Force
}

Get-ChildItem -Path $PythonRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $PythonRoot -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

$docs = Join-Path $AppRoot "docs"
if (Test-Path $docs) {
    Write-Host "==> Removing bundled docs/ (not needed in desktop runtime)"
    Remove-Item -LiteralPath $docs -Recurse -Force
}

$total = (Get-ChildItem $BundleRoot -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
Write-Host ("==> Bundle uncompressed size: {0:N2} GB" -f ($total / 1GB))
