import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.github_content_service import ContentAnalyzer
from src.models.github_models import GitHubProject
from datetime import datetime

def test_system_prompt_enhancement():
    """测试System Prompt增强效果"""
    
    print("🤖 测试System Prompt增强效果")
    print("=" * 50)
    
    # 创建测试项目
    test_project = GitHubProject(
        id="system_prompt_test",
        url="https://github.com/test/awesome-project",
        name="AwesomeProject",
        full_name="test/AwesomeProject",
        description="一个革命性的开源项目，旨在解决现代开发中的核心挑战",
        language="Python",
        stars=15000,
        forks=2000,
        watchers=3000,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        owner="test",
        readme_content="""
# AwesomeProject 🚀

## 简介
这是一个改变游戏规则的Python项目，专注于提升开发效率和代码质量。

## 核心特性
- ⚡ 高性能架构设计
- 🔧 灵活的插件系统
- 🛡️ 企业级安全保障
- 📊 实时监控和分析

## 技术栈
- Python 3.9+
- FastAPI
- PostgreSQL
- Redis
- Docker

## 快速开始
```python
from awesome_project import init_app
app = init_app()
app.run()
```

## 应用场景
适用于企业级应用、数据分析平台、API服务等场景。
        """,
        images=[]
    )
    
    print("📋 测试项目信息:")
    print(f"   项目名称: {test_project.name}")
    print(f"   Star数: {test_project.stars:,}")
    print(f"   技术栈: {test_project.language}")
    print()
    
    # 测试内容生成
    analyzer = ContentAnalyzer()
    metadata = analyzer.analyze_project_content(test_project)
    
    print("🎯 System Prompt增强后的内容:")
    print(f"标题: {metadata.title}")
    print(f"副标题: {metadata.subtitle}")
    print(f"摘要: {metadata.summary}")
    print(f"标签: {', '.join(metadata.tags)}")
    print(f"AI生成: {metadata.ai_generated}")
    print()
    
    # 质量评估
    print("🔍 内容质量评估:")
    
    # 标题质量检查
    title_checks = [
        ('包含项目名', test_project.name in metadata.title),
        ('体现技术', any(tech in metadata.title for tech in ['Python', '项目'])),
        ('长度合适', 20 <= len(metadata.title) <= 40),
        ('有吸引力', any(word in metadata.title for word in ['🔥', '爆款', '推荐', '热门']))
    ]
    
    print("标题质量:")
    for check, passed in title_checks:
        print(f"  {check}: {'✅' if passed else '❌'}")
    
    # 副标题质量检查
    subtitle_checks = [
        ('包含Star信息', any(star_word in metadata.subtitle for star_word in ['Star', 'k+', '热门'])),
        ('补充标题信息', metadata.subtitle != metadata.title),
        ('长度合适', 20 <= len(metadata.subtitle) <= 45)
    ]
    
    print("副标题质量:")
    for check, passed in subtitle_checks:
        print(f"  {check}: {'✅' if passed else '❌'}")
    
    # 摘要质量检查
    summary_checks = [
        ('包含解决问题', any(word in metadata.summary for word in ['解决', '问题'])),
        ('体现技术优势', any(tech in metadata.summary for tech in ['性能', '安全', '监控'])),
        ('长度合适', 100 <= len(metadata.summary) <= 180)
    ]
    
    print("摘要质量:")
    for check, passed in summary_checks:
        print(f"  {check}: {'✅' if passed else '❌'}")
    
    # 标签质量检查
    tag_checks = [
        ('数量固定为10个', len(metadata.tags) == 10),
        ('包含个人IP标签', '#小牛说' in metadata.tags or '#小牛说AI' in metadata.tags),
        ('包含技术/项目相关标签', any(tag in metadata.tags for tag in ['#Python', '#API', '#开发', '#GitHub项目'])),
        ('格式正确', all(tag.startswith('#') for tag in metadata.tags))
    ]
    
    print("标签质量:")
    for check, passed in tag_checks:
        print(f"  {check}: {'✅' if passed else '❌'}")
    
    print("\n🎯 System Prompt增强测试完成!")
    print("💡 增强后的效果：内容更加专业化、一致性更好、质量更高")

if __name__ == "__main__":
    test_system_prompt_enhancement()