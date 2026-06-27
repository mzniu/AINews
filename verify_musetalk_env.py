r"""
验证 musetalk conda 环境是否完整安装。
在 musetalk 环境的 Python 中运行：
  C:\Users\Mingzhu\anaconda3\envs\musetalk\python.exe verify_musetalk_env.py
"""
import sys
import importlib

ENV_PYTHON = sys.executable
print(f"Python: {ENV_PYTHON}")
print(f"Version: {sys.version}")
print()

CHECKS = [
    ("torch",        lambda: __import__("torch").__version__),
    ("cuda",         lambda: str(__import__("torch").cuda.is_available())),
    ("torchvision",  lambda: __import__("torchvision").__version__),
    ("diffusers",    lambda: __import__("diffusers").__version__),
    ("mmengine",     lambda: __import__("mmengine").__version__),
    ("mmcv",         lambda: __import__("mmcv").__version__),
    ("mmcv._ext",    lambda: (importlib.import_module("mmcv._ext"), "OK")[1]),
    ("mmdet",        lambda: __import__("mmdet").__version__),
    ("mmpose",       lambda: __import__("mmpose").__version__),
    ("cv2",          lambda: __import__("cv2").__version__),
    ("face_alignment", lambda: (__import__("face_alignment"), "OK")[1]),
    ("omegaconf",    lambda: __import__("omegaconf").__version__),
    ("transformers", lambda: __import__("transformers").__version__),
]

all_ok = True
for name, check in CHECKS:
    try:
        val = check()
        print(f"  [OK]  {name:<20} {val}")
    except Exception as e:
        print(f"  [FAIL] {name:<20} {e}")
        all_ok = False

print()
if all_ok:
    print("[SUCCESS] MuseTalk 环境验证通过！")
else:
    print("[PARTIAL] 部分依赖缺失，请检查上方错误。")
    sys.exit(1)
