"""
测试改进后的Selenium截图服务
验证超时处理和错误恢复能力
"""

import sys
from pathlib import Path
from services.selenium_screenshot_service import SyncSeleniumScreenshotService

def test_selenium_timeout_handling():
    """测试Selenium超时处理"""
    print("🔍 测试Selenium截图服务超时处理")
    print("=" * 50)
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    # 测试不同的超时设置
    test_cases = [
        {
            'name': '正常超时设置',
            'url': 'https://github.com/ZiYang-xie/WorldGen',
            'timeout': 30,
            'expected': '应该成功'
        },
        {
            'name': '短超时设置',
            'url': 'https://github.com/ZiYang-xie/WorldGen',
            'timeout': 10,
            'expected': '可能超时但仍继续'
        },
        {
            'name': '非常短超时',
            'url': 'https://github.com/ZiYang-xie/WorldGen',
            'timeout': 5,
            'expected': '很可能会超时'
        }
    ]
    
    selenium_service = SyncSeleniumScreenshotService(headless=True)
    
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n🧪 测试案例 {i}: {case['name']}")
        print(f"URL: {case['url']}")
        print(f"超时设置: {case['timeout']}秒")
        print(f"预期结果: {case['expected']}")
        print("-" * 40)
        
        try:
            output_path = Path(f"test_outputs/selenium_timeout_{i}.jpg")
            
            # 执行截图
            result = selenium_service.take_screenshot_sync(
                case['url'],
                output_path,
                width=1920,
                height=1080,
                wait_time=3,
                timeout=case['timeout']
            )
            
            if result and output_path.exists():
                size = output_path.stat().st_size / 1024
                print(f"✅ 成功: 文件大小 {size:.1f} KB")
                results.append({
                    'case': case['name'],
                    'status': 'SUCCESS',
                    'size': f"{size:.1f} KB"
                })
            else:
                print("❌ 失败: 截图未生成")
                results.append({
                    'case': case['name'],
                    'status': 'FAILED',
                    'size': 'N/A'
                })
                
        except Exception as e:
            print(f"❌ 错误: {str(e)[:50]}...")
            results.append({
                'case': case['name'],
                'status': f'ERROR: {str(e)[:30]}',
                'size': 'N/A'
            })
    
    # 输出总结
    print(f"\n📊 测试总结:")
    print("=" * 30)
    for result in results:
        status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
        print(f"{status_icon} {result['case']}: {result['status']} ({result['size']})")
    
    # 清理资源
    selenium_service.stop()
    print(f"\n🧹 Selenium浏览器已停止")

def test_github_integration():
    """测试与GitHub服务的集成"""
    print(f"\n🔗 测试GitHub服务集成")
    print("=" * 30)
    
    try:
        from services.github_screenshot_service import SyncGitHubScreenshotService
        
        github_service = SyncGitHubScreenshotService()
        output_path = Path("test_outputs/github_integration_test.jpg")
        
        result = github_service.take_screenshot_sync(
            "https://github.com/ZiYang-xie/WorldGen",
            output_path
        )
        
        if result and output_path.exists():
            size = output_path.stat().st_size / 1024
            print(f"✅ GitHub集成测试成功: {size:.1f} KB")
        else:
            print("❌ GitHub集成测试失败")
            
    except Exception as e:
        print(f"❌ GitHub集成测试错误: {e}")

if __name__ == "__main__":
    print("🚀 Selenium截图服务优化测试")
    print("=" * 60)
    
    # 测试超时处理
    test_selenium_timeout_handling()
    
    # 测试GitHub集成
    test_github_integration()
    
    print(f"\n🎉 所有测试完成!")