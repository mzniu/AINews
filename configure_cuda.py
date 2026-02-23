"""
CUDA环境配置脚本
用于配置支持GPU加速的PyTorch环境
"""

import os
import subprocess
import sys

def check_cuda_availability():
    """检查CUDA环境"""
    print("🔍 检查CUDA环境...")
    
    try:
        import torch
        print(f"✅ PyTorch版本: {torch.__version__}")
        print(f"✅ CUDA可用: {torch.cuda.is_available()}")
        print(f"✅ CUDA设备数: {torch.cuda.device_count()}")
        
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                print(f"   GPU {i}: {torch.cuda.get_device_name(i)}")
                print(f"   显存: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.1f} GB")
        
        return torch.cuda.is_available()
        
    except ImportError:
        print("❌ PyTorch未安装")
        return False
    except Exception as e:
        print(f"❌ CUDA检查失败: {e}")
        return False

def configure_cuda_environment():
    """配置CUDA环境变量"""
    print("\n🔧 配置CUDA环境变量...")
    
    # 设置环境变量确保使用GPU
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'  # 使用第一个GPU
    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'
    
    print("✅ 已设置 CUDA_VISIBLE_DEVICES=0")
    print("✅ 已设置 PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128")

def test_gpu_performance():
    """测试GPU性能"""
    print("\n⚡ 测试GPU性能...")
    
    try:
        import torch
        
        if not torch.cuda.is_available():
            print("❌ CUDA不可用，跳过GPU测试")
            return
            
        # 创建测试张量
        device = torch.device('cuda')
        print(f"✅ 使用设备: {device}")
        
        # 测试矩阵运算
        size = 1000
        a = torch.randn(size, size, device=device)
        b = torch.randn(size, size, device=device)
        
        # 预热
        for _ in range(3):
            c = torch.mm(a, b)
        
        # 实际测试
        import time
        start_time = time.time()
        for _ in range(10):
            c = torch.mm(a, b)
        end_time = time.time()
        
        avg_time = (end_time - start_time) / 10
        print(f"✅ 矩阵乘法测试完成")
        print(f"   矩阵大小: {size}×{size}")
        print(f"   平均耗时: {avg_time:.4f} 秒")
        print(f"   性能: 约 {2 * size**3 / avg_time / 1e9:.1f} GFLOPS")
        
    except Exception as e:
        print(f"❌ GPU性能测试失败: {e}")

def update_lama_model_config():
    """更新LaMa模型配置以使用GPU"""
    print("\n🔄 更新LaMa模型配置...")
    
    try:
        # 修改watermark_routes.py中的get_lama_model函数
        watermark_file = "api/routes/watermark_routes.py"
        
        if os.path.exists(watermark_file):
            with open(watermark_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 更新设备配置
            if "'cpu'" in content:
                # 检查CUDA是否可用，如果可用则使用GPU
                import torch
                if torch.cuda.is_available():
                    new_content = content.replace("device='cpu'", "device='cuda'")
                    new_content = new_content.replace("'cpu'  # 强制使用CPU", "'cuda'  # 使用GPU加速")
                    
                    with open(watermark_file, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    
                    print("✅ LaMa模型配置已更新为使用GPU")
                else:
                    print("ℹ️  CUDA不可用，保持CPU配置")
            else:
                print("✅ LaMa模型配置已经是最新版本")
        else:
            print("❌ 找不到watermark_routes.py文件")
            
    except Exception as e:
        print(f"❌ 更新LaMa配置失败: {e}")

def main():
    """主函数"""
    print("🚀 CUDA环境配置助手")
    print("=" * 50)
    
    # 检查CUDA环境
    cuda_available = check_cuda_availability()
    
    if not cuda_available:
        print("\n❌ CUDA环境检查失败")
        print("请确保：")
        print("1. 已安装支持CUDA的PyTorch版本")
        print("2. NVIDIA驱动程序已正确安装")
        print("3. GPU设备正常工作")
        return
    
    # 配置环境变量
    configure_cuda_environment()
    
    # 测试GPU性能
    test_gpu_performance()
    
    # 更新模型配置
    update_lama_model_config()
    
    print("\n🎉 CUDA环境配置完成！")
    print("现在可以享受GPU加速的去水印功能了！")

if __name__ == "__main__":
    main()