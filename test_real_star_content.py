import requests
import time

def test_real_project_with_stars():
    """测试真实项目的Star数增强功能"""
    
    print("🚀 测试真实项目的Star数增强功能")
    print("=" * 50)
    
    # 测试几个知名的GitHub项目
    test_projects = [
        {
            'url': 'https://github.com/vuejs/vue',
            'name': 'Vue.js',
            'expected_stars': '30k+'  # 实际应该有3万多stars
        },
        {
            'url': 'https://github.com/facebook/react',
            'name': 'React',
            'expected_stars': '200k+'  # 实际应该有20多万stars
        }
    ]
    
    for i, project in enumerate(test_projects, 1):
        print(f"\n📊 测试项目 {i}: {project['name']}")
        print("-" * 40)
        
        try:
            # 处理项目
            process_payload = {
                'github_url': project['url'],
                'include_screenshots': False,
                'max_images': 2
            }
            
            print("1. 处理项目...")
            process_response = requests.post(
                'http://localhost:8080/api/github/process-project',
                json=process_payload,
                timeout=60
            )
            
            if process_response.status_code == 200:
                process_result = process_response.json()
                project_id = process_result['project_id']
                print(f"✅ 项目处理成功: {project_id}")
                
                # 生成内容
                print("2. 生成AI内容...")
                content_response = requests.post(
                    'http://localhost:8080/api/github/generate-content',
                    json={'project_id': project_id},
                    timeout=30
                )
                
                if content_response.status_code == 200:
                    content_result = content_response.json()
                    metadata = content_result['video_metadata']
                    
                    print(f"标题: {metadata['title']}")
                    print(f"副标题: {metadata['subtitle']}")
                    print(f"摘要: {metadata['summary']}")
                    print(f"标签: {', '.join(metadata['tags'])}")
                    
                    # 检查是否包含Star数相关信息
                    star_indicators = ['爆款', '热门', '推荐', '优质', '新兴', 'Stars', 'Star', 'k+', '数千']
                    title_has_stars = any(indicator in metadata['title'] for indicator in star_indicators)
                    subtitle_has_stars = any(indicator in metadata['subtitle'] for indicator in star_indicators)
                    
                    print(f"\n🔍 Star数信息检查:")
                    print(f"   标题包含Star信息: {'✅' if title_has_stars else '❌'}")
                    print(f"   副标题包含Star信息: {'✅' if subtitle_has_stars else '❌'}")
                    
                    if title_has_stars or subtitle_has_stars:
                        print("🎉 Star数增强功能正常工作!")
                    else:
                        print("⚠️  未检测到明显的Star数信息")
                        
                else:
                    print(f"❌ 内容生成失败: {content_response.status_code}")
            else:
                print(f"❌ 项目处理失败: {process_response.status_code}")
                
        except Exception as e:
            print(f"❌ 测试过程中出现异常: {e}")
        
        # 避免请求过于频繁
        if i < len(test_projects):
            time.sleep(2)
    
    print("\n🎯 Star数增强功能测试完成!")

if __name__ == "__main__":
    test_real_project_with_stars()