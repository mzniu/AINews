import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.github_content_service import ContentAnalyzer
from src.models.github_models import GitHubProject
from datetime import datetime

def test_star_enhanced_content():
    """测试增强的Star数内容生成功能"""
    
    print("⭐ 测试增强的Star数内容生成功能")
    print("=" * 50)
    
    # 创建不同Star数的测试项目
    test_cases = [
        {
            'name': 'HighStarProject',
            'stars': 15000,
            'description': '一个非常流行的开源项目，拥有大量贡献者和用户',
            'language': 'JavaScript'
        },
        {
            'name': 'MediumStarProject',
            'stars': 3500,
            'description': '稳定可靠的Python工具库，受到开发者喜爱',
            'language': 'Python'
        },
        {
            'name': 'LowStarProject',
            'stars': 200,
            'description': '新兴的Rust项目，具有创新特性和良好前景',
            'language': 'Rust'
        }
    ]
    
    analyzer = ContentAnalyzer()
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {case['name']} ({case['stars']} Stars)")
        print("-" * 40)
        
        # 创建测试项目
        test_project = GitHubProject(
            id=f"test_{i}",
            url=f"https://github.com/test/{case['name']}",
            name=case['name'],
            full_name=f"test/{case['name']}",
            description=case['description'],
            language=case['language'],
            stars=case['stars'],
            forks=case['stars'] // 10,
            watchers=case['stars'] // 5,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            owner="test",
            readme_content=f"""
            # {case['name']}
            {case['description']}
            
            ## 特性
            - 高性能
            - 易于使用
            - 社区活跃
            
            ## 技术栈
            {case['language']}, 相关框架
            """,
            images=[]
        )
        
        # 生成内容
        metadata = analyzer.analyze_project_content(test_project)
        
        # 显示结果
        print(f"标题: {metadata.title}")
        print(f"副标题: {metadata.subtitle}")
        print(f"摘要: {metadata.summary}")
        print(f"标签: {', '.join(metadata.tags)}")
        print(f"AI生成: {metadata.ai_generated}")
        
        # 验证Star数相关信息
        star_indicators = ['爆款', '热门', '推荐', '优质', '新兴', 'Stars', 'Star']
        has_star_info = any(indicator in metadata.title or indicator in metadata.subtitle 
                           for indicator in star_indicators)
        
        if has_star_info:
            print("✅ 包含Star数相关信息")
        else:
            print("⚠️  未明显体现Star数信息")
    
    print("\n🎯 测试完成!")

if __name__ == "__main__":
    test_star_enhanced_content()