@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo  EchoMimic V2 Setup (no conda command needed)
echo  Using existing conda env: echomimic_v3
echo  Requires: git, ffmpeg, NVIDIA GPU
echo ============================================================
echo.

set SCRIPT_DIR=%~dp0
set THIRD_PARTY=%SCRIPT_DIR%third_party
set ECHOMIMIC_DIR=%THIRD_PARTY%\echomimic_v2

:: Try known Python locations
set PY=
for %%P in (
    "C:\Users\Mingzhu\anaconda3\envs\echomimic_v3\python.exe"
    "C:\Users\Mingzhu\anaconda3\envs\echomimic\python.exe"
    "%USERPROFILE%\anaconda3\envs\echomimic_v3\python.exe"
    "%USERPROFILE%\anaconda3\envs\echomimic\python.exe"
    "%USERPROFILE%\miniconda3\envs\echomimic_v3\python.exe"
    "%USERPROFILE%\miniconda3\envs\echomimic\python.exe"
) do (
    if exist %%P (
        set PY=%%P
        goto :found_py
    )
)
echo ERROR: No suitable Python found.
echo Please create a Python 3.10 virtual environment with torch 2.5.1+cu124 and set:
echo   set ECHOMIMIC_PYTHON=path\to\python.exe
exit /b 1

:found_py
echo Found Python: %PY%
%PY% --version

:: ---------- Step 1: Clone repo ----------
echo.
echo [1/3] Checking EchoMimic V2 repository...
if not exist "%ECHOMIMIC_DIR%\infer_acc.py" (
    if not exist "%THIRD_PARTY%" mkdir "%THIRD_PARTY%"
    git clone --depth=1 https://github.com/antgroup/echomimic_v2.git "%ECHOMIMIC_DIR%"
    if errorlevel 1 (
        echo ERROR: git clone failed. Check your network.
        exit /b 1
    )
    echo Cloned to %ECHOMIMIC_DIR%
) else (
    echo Already exists: %ECHOMIMIC_DIR%
)

:: ---------- Step 2: Install requirements ----------
echo.
echo [2/3] Installing Python requirements...
%PY% -m pip install -r "%ECHOMIMIC_DIR%\requirements.txt" --quiet
if errorlevel 1 (
    echo WARNING: Some requirements may have failed. Continuing...
)
echo Requirements done.

:: ---------- Step 3: Download model weights ----------
echo.
echo [3/3] Downloading model weights...
%PY% "%SCRIPT_DIR%download_echomimic_models.py"
if errorlevel 1 (
    echo ERROR: Model download failed.
    exit /b 1
)

echo.
echo ============================================================
echo  EchoMimic V2 setup complete!
echo  Env: %PY%
echo  To use: restart web_server.py and select EchoMimic V2 in UI.
echo ============================================================
pause
