"""
单独下载 denoising_unet_acc.pth（使用 ModelScope 镜像）
用法: python download_denoising_unet_acc.py
"""
import sys
import subprocess
from pathlib import Path

WEIGHTS_DIR = Path(__file__).resolve().parent / "third_party" / "echomimic_v2" / "pretrained_weights"
TARGET = WEIGHTS_DIR / "denoising_unet_acc.pth"
EXPECTED_SIZE = 3_400_035_733  # bytes (~3.4 GB)

def check_existing():
    if TARGET.exists():
        size = TARGET.stat().st_size
        if size == EXPECTED_SIZE:
            print(f"✓ denoising_unet_acc.pth 已存在且完整 ({size/1024**3:.2f} GB)")
            return True
        else:
            print(f"⚠ 文件不完整: {size/1024**3:.2f} GB / {EXPECTED_SIZE/1024**3:.2f} GB，重新下载")
            TARGET.unlink()
    return False

def install_modelscope():
    try:
        import modelscope
        print(f"  modelscope {modelscope.__version__} 已安装")
    except ImportError:
        print("  安装 modelscope...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "modelscope", "-q"])

def download_via_modelscope():
    from modelscope.hub.file_download import model_file_download
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  从 ModelScope 下载 denoising_unet_acc.pth → {WEIGHTS_DIR}")
    print("  (文件大小约 3.4 GB，请耐心等待...)")
    try:
        path = model_file_download(
            model_id="BadToBest/EchoMimicV2",
            file_path="denoising_unet_acc.pth",
            local_dir=str(WEIGHTS_DIR),
        )
        print(f"  ✓ 下载完成: {path}")
        return True
    except Exception as e:
        print(f"  ✗ ModelScope 下载失败: {e}")
        return False

def download_via_hf(endpoint: str = "https://huggingface.co"):
    from huggingface_hub import hf_hub_download
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  从 {endpoint} 下载 denoising_unet_acc.pth → {WEIGHTS_DIR}")
    try:
        path = hf_hub_download(
            repo_id="BadToBest/EchoMimicV2",
            filename="denoising_unet_acc.pth",
            local_dir=str(WEIGHTS_DIR),
            endpoint=endpoint,
            force_download=True,
        )
        print(f"  ✓ 下载完成: {path}")
        return True
    except Exception as e:
        print(f"  ✗ HuggingFace 下载失败: {e}")
        return False

def main():
    if check_existing():
        return

    print("[1] 尝试 ModelScope 下载...")
    install_modelscope()
    if download_via_modelscope():
        return

    print("[2] ModelScope 失败，尝试 HuggingFace 官方...")
    if download_via_hf("https://huggingface.co"):
        return

    print("[3] 尝试 hf-mirror...")
    if download_via_hf("https://hf-mirror.com"):
        return

    print("✗ 所有下载方式均失败，请手动下载:")
    print("  https://huggingface.co/BadToBest/EchoMimicV2/resolve/main/denoising_unet_acc.pth")
    print(f"  保存到: {TARGET}")
    sys.exit(1)

if __name__ == "__main__":
    main()
