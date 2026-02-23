"""
CUDA配置验证脚本
验证PyTorch CUDA配置是否正确
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def verify_cuda_setup():
    """验证CUDA设置"""
    print("🔍 CUDA配置验证")
    print("=" * 40)
    
    # 1. 检查PyTorch版本和CUDA支持
    try:
        import torch
        print(f"✅ PyTorch版本: {torch.__version__}")
        print(f"✅ CUDA可用: {torch.cuda.is_available()}")
        print(f"✅ CUDA版本: {torch.version.cuda if torch.cuda.is_available() else 'N/A'}")
        
        if torch.cuda.is_available():
            print(f"✅ CUDA设备数: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"   GPU {i}: {torch.cuda.get_device_name(i)}")
                props = torch.cuda.get_device_properties(i)
                print(f"   显存: {props.total_memory / 1024**3:.1f} GB")
                print(f"   计算能力: {props.major}.{props.minor}")
        else:
            print("⚠️  CUDA不可用，将使用CPU模式")
            
    except ImportError:
        print("❌ PyTorch未安装")
        return False
    except Exception as e:
        print(f"❌ PyTorch检查失败: {e}")
        return False
    
    # 2. 检查环境变量
    print(f"\n🔧 环境变量检查:")
    cuda_visible = os.environ.get('CUDA_VISIBLE_DEVICES', '未设置')
    print(f"   CUDA_VISIBLE_DEVICES: {cuda_visible}")
    
    # 3. 测试简单CUDA操作
    print(f"\n⚡ CUDA功能测试:")
    if torch.cuda.is_available():
        try:
            # 创建CUDA张量
            x = torch.randn(1000, 1000).cuda()
            y = torch.randn(1000, 1000).cuda()
            
            # 执行矩阵乘法
            z = torch.mm(x, y)
            
            # 检查结果
            if z.is_cuda:
                print("✅ CUDA张量操作正常")
                print(f"✅ 结果存储在: {z.device}")
            else:
                print("❌ CUDA张量未在GPU上")
                
        except Exception as e:
            print(f"❌ CUDA操作测试失败: {e}")
            return False
    else:
        print("ℹ️  跳过CUDA操作测试（CUDA不可用）")
    
    # 4. 测试LaMa模型导入
    print(f"\n🎨 LaMa模型测试:")
    try:
        from api.routes.watermark_routes import get_lama_model
        print("✅ 水印路由导入成功")
        
        # 获取模型（这会触发实际加载）
        model = get_lama_model()
        print(f"✅ LaMa模型获取成功")
        print(f"✅ 模型类型: {type(model).__name__}")
        
        # 检查模型设备（如果有）
        if hasattr(model, 'device'):
            print(f"✅ 模型设备: {model.device}")
        
    except Exception as e:
        print(f"❌ LaMa模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def performance_comparison():
    """性能对比测试"""
    print(f"\n⚡ 性能对比测试:")
    
    try:
        import torch
        import time
        
        if not torch.cuda.is_available():
            print("ℹ️  CUDA不可用，跳过性能对比")
            return
            
        # 创建测试数据
        size = 2000
        iterations = 5
        
        print(f"   测试矩阵大小: {size}×{size}")
        print(f"   测试迭代次数: {iterations}")
        
        # CPU测试
        print("   正在测试CPU性能...")
        a_cpu = torch.randn(size, size)
        b_cpu = torch.randn(size, size)
        
        # 预热
        for _ in range(2):
            c = torch.mm(a_cpu, b_cpu)
        
        start_time = time.time()
        for _ in range(iterations):
            c = torch.mm(a_cpu, b_cpu)
        cpu_time = (time.time() - start_time) / iterations
        
        # GPU测试
        print("   正在测试GPU性能...")
        a_gpu = torch.randn(size, size).cuda()
        b_gpu = torch.randn(size, size).cuda()
        
        # 预热
        for _ in range(2):
            c = torch.mm(a_gpu, b_gpu)
        
        torch.cuda.synchronize()
        start_time = time.time()
        for _ in range(iterations):
            c = torch.mm(a_gpu, b_gpu)
        torch.cuda.synchronize()
        gpu_time = (time.time() - start_time) / iterations
        
        # 结果
        speedup = cpu_time / gpu_time
        print(f"✅ CPU平均耗时: {cpu_time:.4f} 秒")
        print(f"✅ GPU平均耗时: {gpu_time:.4f} 秒")
        print(f"✅ GPU加速比: {speedup:.1f}x")
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")

def main():
    """主函数"""
    print("🚀 CUDA配置验证工具")
    print("=" * 50)
    
    # 验证基本配置
    setup_ok = verify_cuda_setup()
    
    if setup_ok:
        # 进行性能测试
        performance_comparison()
        
        print(f"\n🎉 CUDA配置验证通过！")
        print("✅ 您的系统已准备好使用GPU加速的去水印功能")
        print("💡 去水印处理速度将显著提升")
    else:
        print(f"\n❌ CUDA配置存在问题")
        print("请检查：")
        print("1. PyTorch CUDA版本是否正确安装")
        print("2. NVIDIA驱动程序是否最新")
        print("3. GPU是否被其他程序占用")

if __name__ == "__main__":
    main()