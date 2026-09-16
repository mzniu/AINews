# Stop AINews desktop shell and its bundled Python backend before upgrade/install.
$ErrorActionPreference = "SilentlyContinue"

Write-Host "Stopping AINews processes..."
taskkill /F /T /IM ainews-desktop.exe 2>$null | Out-Null
taskkill /F /T /IM AINews.exe 2>$null | Out-Null

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'AINews|web_server\.py' } |
    ForEach-Object {
        Write-Host "  kill python pid $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 2
Write-Host "Done."
