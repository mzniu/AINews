import requests

def test_real_project_enhanced_summary():
    """测试真实项目的增强摘要生成功能"""
    
    print("📝 测试真实项目的增强摘要生成功能")
    print("=" * 50)
    
    # 获取现有项目
    projects = requests.get('http://localhost:8080/api/github/projects').json()
    if projects:
        project_id = projects[0]['id']
        print(f'使用项目: {project_id}')
        
        # 获取项目详细信息
        project_detail = requests.get(f'http://localhost:8080/api/github/projects/{project_id}').json()
        readme_length = len(project_detail['readme_content'])
        print(f'README长度: {readme_length} 字符')
        print(f'README预览: {project_detail["readme_content"][:150]}...')
        print()
        
        # 生成内容（使用增强的摘要功能）
        response = requests.post(
            'http://localhost:8080/api/github/generate-content',
            json={
                'project_id': project_id,
                'selected_images': []
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            metadata = result['video_metadata']
            print('🎯 增强摘要结果:')
            print(f'标题: {metadata["title"]}')
            print(f'副标题: {metadata["subtitle"]}')
            print(f'摘要: {metadata["summary"]}')
            print(f'标签: {", ".join(metadata["tags"])}')
            print()
            
            # 分析摘要质量
            print('🔍 摘要质量分析:')
            summary_length = len(metadata['summary'])
            print(f'摘要长度: {summary_length} 字符')
            
            # 检查是否包含项目相关信息
            project_indicators = ['remotion', 'video', 'react', '动画', '组件', 'motion']
            found_indicators = [indicator for indicator in project_indicators 
                              if indicator.lower() in metadata['summary'].lower()]
            print(f'包含项目关键词: {", ".join(found_indicators) if found_indicators else "无"}')
            
            # 检查技术信息
            tech_indicators = ['react', 'javascript', 'typescript', '框架', '库', 'render']
            has_tech_info = any(indicator in metadata['summary'].lower() for indicator in tech_indicators)
            print(f'包含技术信息: {"✅" if has_tech_info else "❌"}')
            
            # 检查是否比以前更详细
            if summary_length > 80:  # 之前的限制是130，现在允许160
                print('✅ 摘要长度增加，信息更丰富')
            else:
                print('ℹ️  摘要长度适中')
                
        else:
            print('错误:', response.text)
    else:
        print('没有找到项目')

if __name__ == "__main__":
    test_real_project_enhanced_summary()