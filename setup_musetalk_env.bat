@echo off
:: ============================================================
:: setup_musetalk_env.bat
:: 一键创建 MuseTalk 独立 conda 环境
:: ============================================================
setlocal EnableDelayedExpansion

set CONDA_BASE=C:\Users\Mingzhu\anaconda3
set ENV_NAME=musetalk
set PYTHON_VER=3.10
set CUDA_VER=cu118
set TORCH_VER=2.0.1
set TORCHVISION_VER=0.15.2
set TORCHAUDIO_VER=2.0.2

set CONDA_EXE=%CONDA_BASE%\Scripts\conda.exe
set ENV_PYTHON=%CONDA_BASE%\envs\%ENV_NAME%\python.exe

echo ============================================================
echo  MuseTalk conda 环境安装脚本
echo  ENV: %ENV_NAME%  Python: %PYTHON_VER%  CUDA: %CUDA_VER%
echo ============================================================

:: ---------- 检查 conda ----------
if not exist "%CONDA_EXE%" (
    echo [ERROR] 未找到 conda: %CONDA_EXE%
    echo 请先安装 Anaconda / Miniconda。
    pause & exit /b 1
)

:: ---------- 创建或复用 env ----------
if exist "%ENV_PYTHON%" (
    echo [INFO] 环境已存在，跳过创建: %ENV_PYTHON%
    goto :install_deps
)

echo [STEP 1/6] 创建 conda 环境 (Python %PYTHON_VER%)...
call "%CONDA_BASE%\Scripts\activate.bat" base
call conda create -n %ENV_NAME% python=%PYTHON_VER% -y
if errorlevel 1 ( echo [ERROR] conda create 失败 & pause & exit /b 1 )

:install_deps
call "%CONDA_BASE%\Scripts\activate.bat" %ENV_NAME%

echo [STEP 2/6] 安装 PyTorch %TORCH_VER% + CUDA 11.8...
call pip install torch==%TORCH_VER% torchvision==%TORCHVISION_VER% torchaudio==%TORCHAUDIO_VER% --index-url https://download.pytorch.org/whl/%CUDA_VER%
if errorlevel 1 ( echo [ERROR] PyTorch 安装失败 & pause & exit /b 1 )

echo [STEP 3/6] 安装 MuseTalk Python 依赖...
call pip install ^
    diffusers==0.27.2 accelerate omegaconf einops ^
    transformers timm ^
    opencv-python-headless ^
    imageio[ffmpeg] ^
    face-alignment ^
    gfpgan basicsr ^
    huggingface_hub ^
    loguru ^
    pyyaml tqdm
if errorlevel 1 ( echo [WARN] 部分依赖安装失败，继续... )

echo [STEP 4/6] 安装 openmim 并通过 mim 安装 mmlab 套件...
call pip install openmim
call mim install mmengine
call mim install "mmcv==2.0.1"
call mim install "mmdet==3.1.0"
call mim install "mmpose==1.1.0"
if errorlevel 1 ( echo [ERROR] mmlab 套件安装失败 & pause & exit /b 1 )

echo [STEP 5/6] 安装 MuseTalk 自身依赖 (requirements.txt)...
if exist "%~dp0third_party\MuseTalk\requirements.txt" (
    call pip install -r "%~dp0third_party\MuseTalk\requirements.txt" --no-deps
) else (
    echo [WARN] 未找到 requirements.txt，跳过
)

echo [STEP 6/6] 验证安装...
call "%ENV_PYTHON%" -c "import mmcv._ext; print('[OK] mmcv._ext 可用')"
if errorlevel 1 (
    echo [ERROR] mmcv._ext 验证失败，请检查 CUDA 11.8 是否已安装
    echo         下载: https://developer.nvidia.com/cuda-11-8-0-download-archive
    pause & exit /b 1
)
call "%ENV_PYTHON%" -c "import torch; print('[OK] PyTorch', torch.__version__, 'CUDA:', torch.cuda.is_available())"

echo.
echo ============================================================
echo  [SUCCESS] MuseTalk 环境配置完成！
echo  Python 路径: %ENV_PYTHON%
echo.
echo  如需手动指定路径，在启动服务器前设置：
echo    set MUSETALK_PYTHON=%ENV_PYTHON%
echo ============================================================
pause
