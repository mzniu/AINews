# Make bundled venv self-contained: copy stdlib + runtime into PythonRoot and set pyvenv.cfg home.
param(
    [Parameter(Mandatory = $true)]
    [string]$PythonRoot
)

$ErrorActionPreference = "Stop"
$PythonRoot = (Resolve-Path -LiteralPath $PythonRoot).Path
$cfgPath = Join-Path $PythonRoot "pyvenv.cfg"
if (-not (Test-Path $cfgPath)) {
    Write-Host "relocate-bundled-python: no pyvenv.cfg under $PythonRoot (skip)"
    exit 0
}

function Unquote-Home([string]$Value) {
    $v = $Value.Trim()
    if ($v.Length -ge 2 -and $v.StartsWith('"') -and $v.EndsWith('"')) {
        return $v.Substring(1, $v.Length - 2)
    }
    return $v
}

$lines = Get-Content -Path $cfgPath -Encoding UTF8
$homeLine = $lines | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
if (-not $homeLine) {
    Write-Host "relocate-bundled-python: pyvenv.cfg has no home= (skip)"
    exit 0
}

$oldHome = Unquote-Home(($homeLine -replace '^\s*home\s*=\s*', ''))
$version = "3.11.0"
$include = "false"
foreach ($line in $lines) {
    if ($line -match '^\s*version\s*=\s*(.+)$') { $version = $Matches[1].Trim() }
    if ($line -match '^\s*include-system-site-packages\s*=\s*(.+)$') { $include = $Matches[1].Trim() }
}

function Get-StdlibHomeCandidates([string]$Root, [string]$CfgHome) {
    $seen = @{}
    $list = New-Object System.Collections.Generic.List[string]

    function Add-Candidate([string]$Path) {
        if (-not $Path) { return }
        $p = $Path.Trim()
        if ($p -eq '.' -or $p -eq '') { return }
        $key = $p.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { return }
        $seen[$key] = $true
        $list.Add($p)
    }

    $launcher = Join-Path $Root "Scripts\python.exe"
    if (Test-Path $launcher) {
        try {
            $bp = & $launcher -c "import sys; print(sys.base_prefix)" 2>$null
            if ($bp) { Add-Candidate $bp.Trim() }
        } catch {
            # launcher may be broken before relocate; fall through to other candidates
        }
    }

    Add-Candidate $CfgHome
    Add-Candidate "$env:LOCALAPPDATA\Programs\Python\Python311"
    Add-Candidate "$env:ProgramFiles\Python311"
    Add-Candidate "$env:ProgramFiles\Python\Python311"
    return $list
}

$stdlibHomes = Get-StdlibHomeCandidates $PythonRoot $oldHome
$sourceHome = $null
foreach ($candidate in $stdlibHomes) {
    if (Test-Path (Join-Path $candidate "python.exe")) {
        $sourceHome = $candidate
        break
    }
}
if (-not $sourceHome) {
    $sourceHome = $PythonRoot
    if (-not (Test-Path (Join-Path $sourceHome "python.exe"))) {
        Write-Warning "relocate-bundled-python: no base python.exe found; runtime copy may be incomplete"
    }
}

function Paths-Equal([string]$A, [string]$B) {
    if (-not $A -or -not $B) { return $false }
    try {
        $pa = (Resolve-Path -LiteralPath $A).Path
        $pb = (Resolve-Path -LiteralPath $B).Path
        return $pa.Equals($pb, [System.StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

$skipRuntimeCopy = Paths-Equal $sourceHome $PythonRoot
if ($skipRuntimeCopy) {
    Write-Host "relocate-bundled-python: runtime already in PythonRoot (skip exe/dll copy)"
} else {
    $runtimeNames = @(
        "python.exe", "pythonw.exe", "python3.dll",
        "vcruntime140.dll", "vcruntime140_1.dll"
    )
    foreach ($name in $runtimeNames) {
        $src = Join-Path $sourceHome $name
        $dst = Join-Path $PythonRoot $name
        if ((Test-Path $src) -and -not (Paths-Equal $src $dst)) {
            Copy-Item -Path $src -Destination $dst -Force
        }
    }
    Get-ChildItem -Path $sourceHome -Filter "python3*.dll" -ErrorAction SilentlyContinue | ForEach-Object {
        $dst = Join-Path $PythonRoot $_.Name
        if (-not (Paths-Equal $_.FullName $dst)) {
            Copy-Item -Path $_.FullName -Destination $dst -Force
        }
    }

    foreach ($zip in Get-ChildItem -Path $sourceHome -Filter "python*.zip" -ErrorAction SilentlyContinue) {
        $dst = Join-Path $PythonRoot $zip.Name
        if (-not (Paths-Equal $zip.FullName $dst)) {
            Copy-Item -Path $zip.FullName -Destination $dst -Force
        }
    }
}

function Ensure-PortableStdlib([string]$Root, $Candidates) {
    $libDst = Join-Path $Root "Lib"
    New-Item -ItemType Directory -Force -Path $libDst | Out-Null
    $stdlibExclude = @("site-packages", "test", "idlelib", "turtledemo", "tkinter", "__pycache__")

    $hasZip = @(Get-ChildItem -Path $Root -Filter "python*.zip" -ErrorAction SilentlyContinue).Count -gt 0
    if (-not $hasZip) {
        foreach ($candidate in $Candidates) {
            foreach ($zip in Get-ChildItem -Path $candidate -Filter "python*.zip" -ErrorAction SilentlyContinue) {
                $dst = Join-Path $Root $zip.Name
                if (-not (Paths-Equal $zip.FullName $dst)) {
                    Copy-Item -Path $zip.FullName -Destination $dst -Force
                }
                Write-Host "relocate-bundled-python: copied stdlib $($zip.Name)"
                $hasZip = $true
                break
            }
            if ($hasZip) { break }
        }
    }

    $hasEncodingsDir = Test-Path (Join-Path $libDst "encodings")
    if (-not $hasEncodingsDir -and -not $hasZip) {
        foreach ($candidate in $Candidates) {
            $libSrc = Join-Path $candidate "Lib"
            if (-not (Test-Path (Join-Path $libSrc "encodings"))) { continue }
            Write-Host "relocate-bundled-python: merging stdlib Lib from $candidate (excluding site-packages)"
            Get-ChildItem -Path $libSrc -Force | Where-Object { $stdlibExclude -notcontains $_.Name } | ForEach-Object {
                Copy-Item -Path $_.FullName -Destination (Join-Path $libDst $_.Name) -Recurse -Force
            }
            break
        }
    }

    if ($hasZip -and (Test-Path $libDst)) {
        Get-ChildItem -Path $libDst -Force | Where-Object { $_.Name -ne "site-packages" } | ForEach-Object {
            Write-Host "relocate-bundled-python: trimming Lib\$($_.Name) (stdlib in python*.zip)"
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }
}

Ensure-PortableStdlib $PythonRoot $stdlibHomes

function Merge-DllsFrom([string]$FromHome, [string]$IntoRoot) {
    if (Paths-Equal $FromHome $IntoRoot) { return $true }
    $dllsSrc = Join-Path $FromHome "DLLs"
    if (-not (Test-Path $dllsSrc)) { return $false }
    $dllsDst = Join-Path $IntoRoot "DLLs"
    if (Test-Path $dllsDst) {
        $item = Get-Item -LiteralPath $dllsDst
        if (-not $item.PSIsContainer) {
            Remove-Item -LiteralPath $dllsDst -Force
        }
    }
    New-Item -ItemType Directory -Force -Path $dllsDst | Out-Null
    Get-ChildItem -Path $dllsSrc -Force | ForEach-Object {
        $dst = Join-Path $dllsDst $_.Name
        if (Paths-Equal $_.FullName $dst) { return }
        Copy-Item -Path $_.FullName -Destination $dst -Recurse -Force
    }
    return $true
}

$dllsMerged = Merge-DllsFrom $sourceHome $PythonRoot
if (-not $dllsMerged) {
    foreach ($candidate in $stdlibHomes) {
        if (Merge-DllsFrom $candidate $PythonRoot) { break }
    }
}

$hasEncodingsDir = Test-Path (Join-Path $PythonRoot "Lib\encodings")
$hasStdlibZip = @(Get-ChildItem -Path $PythonRoot -Filter "python*.zip" -ErrorAction SilentlyContinue).Count -gt 0
if (-not $hasEncodingsDir -and -not $hasStdlibZip) {
    throw "relocate-bundled-python: no stdlib (Lib\encodings or python*.zip) under $PythonRoot"
}

$portableExe = Join-Path $PythonRoot "python.exe"
if (Test-Path $portableExe) {
    $env:PYTHONHOME = $PythonRoot
    & $portableExe -c "import encodings" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "relocate-bundled-python: portable python cannot import encodings"
    }
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
}

$newCfg = @(
    "home = $PythonRoot"
    "include-system-site-packages = $include"
    "version = $version"
) -join "`n"
$newCfg += "`n"
Set-Content -Path $cfgPath -Value $newCfg -Encoding UTF8 -NoNewline

Write-Host "relocate-bundled-python: portable venv ready (home = $PythonRoot)"
