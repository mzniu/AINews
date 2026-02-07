"""测试数据生成器 - 用于开发和测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from src.models.article import Article
import json


def generate_mock_articles():
    """生成模拟文章数据"""
    articles = [
        Article(
            id="mock_001",
            title="DeepSeek发布最新大模型，性能超越GPT-4",
            url="https://www.jiqizhixin.com/articles/2026-02-05-1",
            source="jiqizhixin",
            author="机器之心",
            publish_time=datetime(2026, 2, 5, 10, 30),
            content="""
            国内AI公司DeepSeek今日发布最新一代大语言模型DeepSeek-V3，
            据官方称该模型在多项基准测试中超越了GPT-4。
            
            主要亮点：
            1. 参数规模达到千亿级别
            2. 支持32K上下文长度
            3. 推理速度提升50%
            4. 中文理解能力显著提升
            
            该模型将通过API形式对外开放，定价极具竞争力。
            """,
            summary="DeepSeek发布V3大模型，性能超越GPT-4，支持32K上下文",
            tags=["DeepSeek", "大模型", "GPT-4", "中文NLP"],
            images=[
                "https://example.com/image1.jpg",
                "https://example.com/image2.jpg"
            ]
        ),
        Article(
            id="mock_002",
            title="OpenAI推出视频生成模型Sora升级版",
            url="https://www.jiqizhixin.com/articles/2026-02-05-2",
            source="jiqizhixin",
            author="量子位",
            publish_time=datetime(2026, 2, 5, 14, 20),
            content="""
            OpenAI宣布Sora视频生成模型迎来重大升级，支持更长时间、
            更高分辨率的视频生成。
            
            新功能包括：
            - 支持生成最长2分钟的4K视频
            - 改进的物理模拟和一致性
            - 更好的文字理解能力
            - 降低生成时间50%
            
            目前已向Plus用户开放测试。
            """,
            summary="OpenAI升级Sora，支持2分钟4K视频生成",
            tags=["OpenAI", "Sora", "视频生成", "AIGC"],
            images=["https://example.com/sora.jpg"]
        ),
        Article(
            id="mock_003",
            title="谷歌Gemini 2.0发布，多模态能力全面提升",
            url="https://www.jiqizhixin.com/articles/2026-02-05-3",
            source="jiqizhixin",
            author="新智元",
            publish_time=datetime(2026, 2, 5, 16, 45),
            content="""
            谷歌正式发布Gemini 2.0，这是其下一代多模态AI模型。
            
            核心改进：
            1. 图像理解准确率提升30%
            2. 支持实时语音对话
            3. 原生支持代码生成和调试
            4. 长文档理解能力增强
            
            Gemini 2.0将整合到Google所有产品线中。
            """,
            summary="谷歌发布Gemini 2.0，多模态能力全面提升",
            tags=["Google", "Gemini", "多模态", "AI"],
            images=[]
        ),
    ]
    
    return articles


def save_mock_data():
    """保存模拟数据到文件"""
    articles = generate_mock_articles()
    
    output_dir = Path("data/raw/jiqizhixin")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "mock_articles.json"
    
    data = [article.to_dict() for article in articles]
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 模拟数据已保存到: {output_file}")
    print(f"📊 共生成 {len(articles)} 篇文章")
    
    for i, article in enumerate(articles, 1):
        print(f"\n[{i}] {article.title}")
        print(f"    来源: {article.source}")
        print(f"    时间: {article.publish_time}")
        print(f"    标签: {', '.join(article.tags)}")


if __name__ == "__main__":
    save_mock_data()
