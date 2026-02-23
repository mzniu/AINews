import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.github_content_service import ContentAnalyzer
from src.models.github_models import GitHubProject
from datetime import datetime

def test_enhanced_summary_generation():
    """测试增强的摘要生成功能（使用完整README）"""
    
    print("📝 测试增强的摘要生成功能")
    print("=" * 50)
    
    # 创建测试项目，包含丰富的README内容
    test_project = GitHubProject(
        id="enhanced_summary_test",
        url="https://github.com/test/enhanced-project",
        name="EnhancedProject",
        full_name="test/EnhancedProject",
        description="一个功能强大的现代化Web框架，专为高性能应用而设计",
        language="TypeScript",
        stars=8500,
        forks=1200,
        watchers=2500,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        owner="test",
        readme_content="""
# EnhancedProject 🚀

一个现代化的TypeScript Web框架，专注于性能和开发者体验。

## 🌟 核心特性

### ⚡ 高性能
- 基于V8引擎优化的运行时
- 零配置的构建系统
- 内置缓存和预渲染机制

### 🛠 开发者友好
- 类型安全的API设计
- 丰富的插件生态系统
- 详细的文档和示例

### 📱 多平台支持
- Web应用开发
- 移动端Hybrid应用
- 桌面应用Electron支持

## 🚀 快速开始

```bash
npm install enhanced-project
```

```typescript
import { createApp } from 'enhanced-project'

const app = createApp({
  name: 'My Awesome App',
  plugins: ['router', 'state-management']
})

app.start()
```

## 📊 性能对比

相比传统框架，EnhancedProject在以下方面表现优异：
- 启动速度提升40%
- 内存占用减少30%  
- 开发体验显著改善

## 🤝 贡献指南

欢迎提交Issue和Pull Request！查看我们的[贡献指南](CONTRIBUTING.md)了解更多详情。

## 📄 许可证

MIT License - 查看[LICENSE](LICENSE)文件了解详情
        """,
        images=[]
    )
    
    print("📋 测试项目信息:")
    print(f"   项目名称: {test_project.name}")
    print(f"   Star数: {test_project.stars}")
    print(f"   README长度: {len(test_project.readme_content)} 字符")
    print(f"   README预览: {test_project.readme_content[:100]}...")
    print()
    
    # 测试内容生成
    analyzer = ContentAnalyzer()
    metadata = analyzer.analyze_project_content(test_project)
    
    print("🎯 生成结果:")
    print(f"标题: {metadata.title}")
    print(f"副标题: {metadata.subtitle}")
    print(f"摘要: {metadata.summary}")
    print(f"标签: {', '.join(metadata.tags)}")
    print(f"AI生成: {metadata.ai_generated}")
    print()
    
    # 分析摘要质量
    print("🔍 摘要质量分析:")
    
    # 检查是否包含关键信息
    key_terms = ['性能', 'TypeScript', 'Web框架', '开发者', '插件', '生态系统']
    found_terms = [term for term in key_terms if term in metadata.summary]
    
    print(f"包含的关键术语: {', '.join(found_terms) if found_terms else '无'}")
    print(f"摘要长度: {len(metadata.summary)} 字符")
    
    # 检查摘要完整性
    completeness_indicators = ['解决', '功能', '特性', '优势', '价值']
    has_completeness = any(indicator in metadata.summary for indicator in completeness_indicators)
    print(f"包含完整性描述: {'✅' if has_completeness else '❌'}")
    
    # 检查技术信息
    tech_indicators = ['TypeScript', '框架', '性能', '开发']
    has_tech_info = any(indicator in metadata.summary for indicator in tech_indicators)
    print(f"包含技术信息: {'✅' if has_tech_info else '❌'}")
    
    print("\n🎯 测试完成!")

if __name__ == "__main__":
    test_enhanced_summary_generation()