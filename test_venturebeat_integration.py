"""
VentureBeat爬虫集成测试
测试index.html网页爬取功能中的VentureBeat文章抓取
"""
import requests
import json
import time

def test_index_integration():
    """测试index.html集成的VentureBeat爬取功能"""
    
    print("🚀 测试index.html集成的VentureBeat爬虫功能")
    print("=" * 60)
    
    # 测试URL
    test_url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    
    # 使用普通的fetch-url接口（会自动识别VentureBeat URL并转发）
    url = "http://localhost:8080/api/fetch-url"
    payload = {
        "url": test_url
    }
    
    try:
        print(f"正在测试URL: {test_url}")
        print("使用普通接口，系统会自动识别并使用专门的VentureBeat处理逻辑")
        
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120  # 增加超时时间因为要下载图片
        )
        
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            result_data = data.get('data', {})
            
            print("\n✅ 爬取成功!")
            print(f"标题: {result_data.get('title', 'N/A')}")
            print(f"作者: {result_data.get('author', 'N/A')}")
            print(f"内容长度: {result_data.get('content_length', 0)} 字符")
            print(f"图片数量: {result_data.get('images_count', 0)} 张")
            print(f"抓取时间: {result_data.get('crawl_time', 'N/A')}")
            print(f"来源: {result_data.get('source', 'N/A')}")
            
            # 显示图片信息
            images = result_data.get('images', [])
            if images:
                print(f"\n🖼️  图片列表 ({len(images)} 张):")
                for i, img in enumerate(images[:3]):  # 只显示前3张
                    img_url = img.get('url', 'N/A')
                    success = img.get('success', False)
                    print(f"  {i+1}. {'✅' if success else '❌'} {img_url[:60]}...")
            
            # 显示内容预览
            content_preview = result_data.get('content_preview', '')
            if content_preview:
                print(f"\n📝 内容预览:")
                print(f"  {content_preview[:200]}...")
            
            # 显示文件路径
            content_file = result_data.get('content_file', '')
            metadata_file = result_data.get('metadata_file', '')
            if content_file:
                print(f"\n📂 文件位置:")
                print(f"  内容文件: {content_file}")
                print(f"  元数据文件: {metadata_file}")
            
            return True
            
        else:
            print(f"❌ 请求失败: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False

def test_direct_venturebeat_api():
    """直接测试VentureBeat专用API"""
    
    print("\n" + "=" * 60)
    print("🧪 直接测试VentureBeat专用API端点")
    print("=" * 60)
    
    url = "http://localhost:8080/api/fetch-venturebeat"
    payload = {
        "url": "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    }
    
    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 专用API调用成功!")
            print(f"消息: {data.get('message', 'N/A')}")
            return True
        else:
            print(f"❌ 专用API调用失败: {response.status_code}")
            print(f"错误详情: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 专用API测试异常: {e}")
        return False

def main():
    """主测试函数"""
    print("🌐 AINews VentureBeat爬虫集成测试")
    print("测试环境: http://localhost:8080")
    print("=" * 60)
    
    # 测试直接API
    direct_success = test_direct_venturebeat_api()
    
    # 等待一下避免请求过于频繁
    time.sleep(2)
    
    # 测试集成API
    integration_success = test_index_integration()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结:")
    print(f"  专用API测试: {'✅ 通过' if direct_success else '❌ 失败'}")
    print(f"  集成API测试: {'✅ 通过' if integration_success else '❌ 失败'}")
    
    if direct_success and integration_success:
        print("\n🎉 所有测试通过！VentureBeat爬虫集成成功！")
        print("\n💡 功能特点:")
        print("  • 自动识别VentureBeat URL")
        print("  • 异步爬取提高性能")
        print("  • 智能图片下载和验证")
        print("  • 完整的元数据提取")
        print("  • 与现有index.html界面无缝集成")
    else:
        print("\n⚠️  部分测试失败，请检查配置")

if __name__ == "__main__":
    main()