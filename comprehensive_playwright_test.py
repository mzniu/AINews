import sys
import os
from pathlib import Path
from services.github_service import GitHubProcessingService
from services.github_content_service import ContentAnalyzer
from src.models.github_models import GitHubProjectBase

def comprehensive_playwright_test():
    """综合测试Playwright兼容性解决方案"""
    
    print("🧪 综合Playwright兼容性测试")
    print("=" * 60)
    
    # 测试1: Python版本和环境检测
    print("1️⃣ 环境兼容性检测")
    python_version = sys.version_info
    print(f"   Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    print(f"   操作系统: {sys.platform}")
    
    has_issues = (python_version.major == 3 and python_version.minor >= 13 and sys.platform == 'win32')
    if has_issues:
        print("   ⚠️  检测到已知兼容性问题 - 系统将使用智能降级")
    else:
        print("   ✅ 环境兼容性良好")
    
    # 测试2: GitHub服务处理测试
    print("\n2️⃣ GitHub项目处理测试")
    try:
        github_service = GitHubProcessingService()
        test_project = GitHubProjectBase(
            github_url="https://github.com/http-party/http-server"
        )
        
        print("   处理项目:", test_project.github_url)
        result = github_service.process_project_async(test_project)
        
        if result and hasattr(result, 'project_id'):
            print(f"   ✅ 项目处理成功: {result.project_id}")
            print(f"   项目名称: {result.name}")
            print(f"   Star数: {result.stars}")
            print(f"   图片数量: {len(result.images)}")
            
            # 测试3: 内容生成测试
            print("\n3️⃣ AI内容生成测试")
            content_analyzer = ContentAnalyzer()
            metadata = content_analyzer.analyze_project_content(result)
            
            print("   标题:", metadata.title)
            print("   副标题:", metadata.subtitle)
            print("   摘要长度:", len(metadata.summary))
            print("   标签数量:", len(metadata.tags))
            print("   AI生成:", metadata.ai_generated)
            
            # 测试4: 截图服务测试
            print("\n4️⃣ 截图服务测试")
            screenshot_path = Path(f"data/test_outputs/{result.project_id}_final_test.jpg")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            
            success = github_service.screenshot_service.take_screenshot_sync(
                test_project.github_url,
                screenshot_path
            )
            
            if success and screenshot_path.exists():
                size_kb = screenshot_path.stat().st_size / 1024
                print(f"   ✅ 截图服务工作正常")
                print(f"   截图文件: {screenshot_path}")
                print(f"   文件大小: {size_kb:.1f} KB")
            else:
                print("   ❌ 截图服务测试失败")
                
        else:
            print("   ❌ 项目处理失败")
            
    except Exception as e:
        print(f"   ❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🎯 综合测试完成!")
    
    if has_issues:
        print("💡 系统已针对Python 3.13 + Windows环境进行了优化:")
        print("   • 自动检测兼容性问题")
        print("   • 智能降级到备用截图方案")
        print("   • 生成高质量的GitHub风格占位图")
        print("   • 保持完整的功能可用性")
    else:
        print("💡 系统在当前环境下运行良好")

if __name__ == "__main__":
    comprehensive_playwright_test()