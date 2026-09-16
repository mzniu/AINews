# Copy rebuilt ainews-desktop.exe + icons into Program Files and refresh the shell.
# Run elevated (UAC).
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ExeSrc = Join-Path $RepoRoot "desktop\src-tauri\target\release\ainews-desktop.exe"
$ExeDst = Join-Path $env:ProgramFiles "AINews\ainews-desktop.exe"
$FavDstDir = Join-Path $env:ProgramFiles "AINews\bundle-resources\app\static"

if (-not (Test-Path $ExeSrc)) {
    throw "Rebuilt exe not found: $ExeSrc"
}

& (Join-Path $PSScriptRoot "stop-ainews.ps1")
Copy-Item $ExeSrc $ExeDst -Force
Copy-Item (Join-Path $RepoRoot "static\favicon.png") (Join-Path $FavDstDir "favicon.png") -Force
Copy-Item (Join-Path $RepoRoot "static\favicon.ico") (Join-Path $FavDstDir "favicon.ico") -Force

$sh = New-Object -ComObject WScript.Shell
$links = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\AINews.lnk",
    "$env:USERPROFILE\Desktop\AINews.lnk"
)
foreach ($path in $links) {
    $dir = Split-Path $path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    $lnk = $sh.CreateShortcut($path)
    $lnk.TargetPath = $ExeDst
    $lnk.WorkingDirectory = Split-Path $ExeDst
    $lnk.IconLocation = "$ExeDst,0"
    $lnk.Description = "AINews"
    $lnk.Save()
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class ShellNotify {
  [DllImport("shell32.dll")]
  public static extern void SHChangeNotify(uint wEventId, uint uFlags, IntPtr dwItem1, IntPtr dwItem2);
}
"@
[ShellNotify]::SHChangeNotify(0x8000000, 0x1000, [IntPtr]::Zero, [IntPtr]::Zero)
ie4uinit.exe -show | Out-Null
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Remove-Item "$env:LOCALAPPDATA\IconCache.db" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\Microsoft\Windows\Explorer\iconcache*" -Force -ErrorAction SilentlyContinue
Start-Process explorer.exe
Start-Sleep -Seconds 2
Start-Process $ExeDst
Write-Host "Taskbar/Start icon refresh done."
