"""
AI内容分析服务
基于项目内容自动生成视频标题、副标题、摘要和标签
"""
import re
from typing import List, Dict, Optional, Tuple
from loguru import logger
from openai import OpenAI
from dotenv import load_dotenv
import os

from src.models.github_models import VideoMetadata, GitHubProject

# 加载环境变量
load_dotenv()

class ContentAnalyzer:
    """内容分析器基类"""
    
    def __init__(self):
        self.client = None
        api_key = os.getenv('DEEPSEEK_API_KEY') or os.getenv('OPENAI_API_KEY')
        if api_key:
            self.client = OpenAI(
                api_key=api_key,
                base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
            )
    
    def analyze_project_content(self, project: GitHubProject) -> VideoMetadata:
        """
        分析项目内容并生成视频元数据
        """
        if not self.client:
            logger.warning("未配置AI API密钥，使用默认内容生成")
            return self._generate_default_content(project)
        
        try:
            # 提取关键信息
            project_info = self._extract_project_info(project)
            
            # 生成各部分内容
            title = self._generate_title(project_info)
            subtitle = self._generate_subtitle(project_info,title)
            summary = self._generate_summary(project_info)
            tags = self._generate_tags(project_info)
            
            return VideoMetadata(
                title=title,
                subtitle=subtitle,
                summary=summary,
                tags=tags,
                ai_generated=True,
                confidence_score=0.9
            )
            
        except Exception as e:
            logger.error(f"AI内容生成失败: {e}")
            return self._generate_default_content(project)
    
    def _extract_project_info(self, project: GitHubProject) -> Dict:
        """提取项目关键信息"""
        info = {
            'name': project.name,
            'full_name': project.full_name,
            'description': project.description or '',
            'language': project.language or '',
            'stars': project.stars,
            'readme_content': project.readme_content or '',
            'image_count': len(project.images)
        }
        
        # 提取技术栈
        info['tech_stack'] = self._extract_technologies(info)
        
        # 提取项目特点
        info['features'] = self._extract_features(info)
        
        return info
    
    def _extract_technologies(self, info: Dict) -> List[str]:
        """从项目信息中提取技术栈"""
        technologies = []
        
        # 从编程语言推断
        if info['language']:
            technologies.append(info['language'])
        
        # 从README中提取技术关键词
        readme = info['readme_content'].lower()
        tech_keywords = [
            'react', 'vue', 'angular', 'node.js', 'python', 'java', 'go', 'rust',
            'docker', 'kubernetes', 'tensorflow', 'pytorch', 'flutter', 'swift',
            'mongodb', 'postgresql', 'redis', 'nginx', 'aws', 'azure', 'gcp'
        ]
        
        for tech in tech_keywords:
            if tech in readme:
                technologies.append(tech.title())
        
        return list(set(technologies))[:5]  # 最多返回5个技术
    
    def _extract_features(self, info: Dict) -> List[str]:
        """提取项目主要特性"""
        features = []
        readme = info['readme_content'].lower()
        
        # 常见特性关键词
        feature_patterns = [
            (r'fast', '高性能'),
            (r'easy', '易用'),
            (r'secure', '安全性强'),
            (r'scalable', '可扩展'),
            (r'real.time', '实时'),
            (r'cross.platform', '跨平台'),
            (r'open.source', '开源'),
            (r'microservice', '微服务'),
            (r'api', 'API驱动'),
            (r'cli', '命令行工具')
        ]
        
        for pattern, feature in feature_patterns:
            if re.search(pattern, readme):
                features.append(feature)
        
        return features[:3]  # 最多返回3个特性
    
    def _generate_title(self, info: Dict) -> str:
        """生成吸引人的标题"""
        try:
            system_prompt = """
            你是一位专业的技术内容创作者，专门为GitHub开源项目制作短视频内容。
            你的任务是基于项目信息生成吸引人的中文视频标题。
            
            内容风格要求：
            - 突出项目的技术亮点和实用价值
            - 使用适度的营销语言，但保持真实性
            - 标题长度控制在25-30个字符
            - 必须包含项目核心技术和名称
            - 体现"GitHub飙升榜"的概念
            """
            
            user_prompt = f"""
            基于以下GitHub项目信息，生成一个吸引人的中文视频标题：
            
            项目名称: {info['name']}
            描述: {info['description']}
            技术栈: {', '.join(info['tech_stack'])}
            特点: {', '.join(info['features'])}
            Star数: {info['stars']}
            完整README内容:
            {info['readme_content']}

            要求：
            1. 标题包含项目名称，突出项目的核心价值和亮点
            2. 使用有些夸张并吸引眼球的词汇
            3. 体现技术特色
            4. 保持简洁有力
            5. 直接返回标题，不要其他内容
            6. 突出此项目是Github飙升榜的项目
            ## 标题中务必包含项目名称：{info['name']}
            """
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=50,
                temperature=0.75
            )
            
            title = response.choices[0].message.content.strip()            
            return title
            
        except Exception as e:
            logger.error(f"生成标题失败: {e}")
            return self._generate_default_title(info)
    
    def _generate_subtitle(self, info: Dict, title) -> str:
        """生成副标题（包含Star数信息）""" 
        try:
            # 构造Star数描述
            star_description = self._format_star_count(info['stars'])
            
            system_prompt = """
            你是一位专业的视频内容策划师，负责为GitHub项目生成吸引人的副标题。
            
            副标题创作原则：
            - 补充主标题信息，突出不同角度的价值
            - 重点强调项目的社会影响力和受欢迎程度
            - 结合Star数展现项目的社区认可度
            - 长度控制在25-35个字符
            - 避免与主标题内容重复
            - 突出项目的实际应用价值和技术优势
            """
            
            user_prompt = f"""
            为以下GitHub项目生成一个中文副标题，突出Star数优势：
            
            项目名称: {info['name']}
            主标题: {title}
            描述: {info['description']}
            技术栈: {', '.join(info['tech_stack'])}
            Star数: {info['stars']} ({star_description})
            完整README内容: 
            {info['readme_content']}

            要求：
            1. 强调项目的受欢迎程度（Star数）
            2. 强调项目解决了什么问题
            3. 增强可信度和吸引力
            4. 保持简洁有力
            5. 直接返回副标题，不要其他内容
            6. 不要和主标题内容相似，突出其他特点
            """
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=60,
                temperature=0.75
            )
            
            subtitle = response.choices[0].message.content.strip()
            return subtitle[:40] + ("..." if len(subtitle) > 40 else "")
            
        except Exception as e:
            logger.error(f"生成副标题失败: {e}")
            return self._generate_default_subtitle_with_stars(info)
    
    def _generate_summary(self, info: Dict) -> str:
        """生成项目摘要（使用完整README内容）"""
        try:
            # 使用完整的README内容
            full_readme = info['readme_content']
            
            system_prompt = """
            你是一位技术文档专家，擅长将复杂的GitHub项目信息提炼成简洁有力的摘要。
            
            摘要写作要求：
            - 长度控制在120-150个字符
            - 突出项目解决的核心问题
            - 强调技术优势和创新点
            - 体现项目的实用价值
            - 语言通俗易懂，避免过多技术术语
            - 基于真实的README内容，保持准确性
            """
            
            user_prompt = f"""
            基于以下完整的GitHub项目README内容，生成一段中文摘要：
            
            项目名称: {info['name']}
            项目描述: {info['description']}
            技术栈: {', '.join(info['tech_stack'])}
            特点: {', '.join(info['features'])}
            Star数: {info['stars']}
            
            完整README内容:
            {full_readme}
            
            要求：
            1. 简洁明了介绍项目核心功能
            2. 突出解决的实际问题
            3. 说明主要特性和技术优势
            4. 直接返回摘要，不要其他内容
            5. 突出项目的核心价值和亮点
            """
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.75
            )
            
            summary = response.choices[0].message.content.strip()
            return summary[:160] + ("..." if len(summary) > 160 else "")
            
        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            return self._generate_default_summary(info)
    
    def _generate_tags(self, info: Dict) -> List[str]:
        """生成相关标签"""
        try:
            system_prompt = """
            你是一位社交媒体内容专家，擅长为技术项目创建精准的标签体系。
            
            标签创建原则：
            - 包括技术栈标签、功能特性标签、应用领域标签
            - 使用简洁准确的中文词汇
            - 避免过于宽泛或重复的标签
            - 考虑SEO优化和搜索可见性
            - 标签数量控制在5-8个
            - 格式：每个标签用逗号分隔
            """
            
            user_prompt = f"""
            为以下GitHub项目生成5-8个相关的中文标签：
            
            项目名称: {info['name']}
            技术栈: {', '.join(info['tech_stack'])}
            特点: {', '.join(info['features'])}
            
            要求：
            1. 给出10个标签，包括技术标签、功能标签、领域标签
            2. 使用简洁的中文词汇
            3. 用空格分隔各个标签，标签以#开头，如：#python #项目 #开源
            4. 直接返回标签列表，不要其他内容
            """
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=60,
                temperature=0.4
            )
            
            tags_text = response.choices[0].message.content.strip()
            tags = [tag.strip() for tag in tags_text.split(',')]
            return tags[:8]
            
        except Exception as e:
            logger.error(f"生成标签失败: {e}")
            return self._generate_default_tags(info)
    
    def _generate_default_content(self, project: GitHubProject) -> VideoMetadata:
        """生成默认内容（当AI不可用时）"""
        info = self._extract_project_info(project)
        
        return VideoMetadata(
            title=self._generate_default_title(info),
            subtitle=self._generate_default_subtitle(info),
            summary=self._generate_default_summary(info),
            tags=self._generate_default_tags(info),
            ai_generated=False,
            confidence_score=0.7
        )
    
    def _generate_default_title(self, info: Dict) -> str:
        """生成默认标题（突出Star数）"""
        tech_part = f"[{info['language']}]" if info['language'] else ""
        
        # 根据Star数调整标题强度
        if info['stars'] >= 10000:
            popularity = "🔥爆款"
        elif info['stars'] >= 5000:
            popularity = "⭐热门"
        elif info['stars'] >= 1000:
            popularity = "🌟推荐"
        elif info['stars'] >= 500:
            popularity = "✨优质"
        else:
            popularity = "🚀新兴"
            
        return f"{popularity}{info['name']}{tech_part}"
    
    def _format_star_count(self, stars: int) -> str:
        """格式化Star数为友好的描述"""
        if stars >= 10000:
            return f"{stars//1000}k+ Stars"
        elif stars >= 5000:
            return f"{stars//1000}.{(stars%1000)//100}k Stars"
        elif stars >= 1000:
            return f"数千Stars"
        elif stars >= 500:
            return f"高Star项目"
        elif stars >= 100:
            return f"百Stars项目"
        else:
            return f"新兴项目"
    
    def _generate_default_subtitle_with_stars(self, info: Dict) -> str:
        """生成包含Star数信息的默认副标题"""
        star_desc = self._format_star_count(info['stars'])
        feature_text = " · ".join(info['features']) if info['features'] else "功能完善"
        
        # 根据Star数调整副标题重点
        if info['stars'] >= 1000:
            return f"{star_desc} | {feature_text}"
        elif info['stars'] >= 100:
            return f"{star_desc} | {feature_text}"
        else:
            return f"{feature_text} | {info['language']}项目"
    
    def _generate_default_summary(self, info: Dict) -> str:
        """生成默认摘要"""
        desc = info['description'] or f"这是一个优秀的{info['language']}项目"
        tech_text = f"，使用{', '.join(info['tech_stack'])}技术栈" if info['tech_stack'] else ""
        return f"{desc}{tech_text}，值得关注和学习。"
    
    def _generate_default_tags(self, info: Dict) -> List[str]:
        """生成默认标签"""
        tags = ['GitHub项目', '开源软件']
        if info['language']:
            tags.append(info['language'])
        if info['tech_stack']:
            tags.extend(info['tech_stack'][:3])
        return tags[:6]


class ContentStyleManager:
    """内容风格管理器"""
    
    STYLES = {
        'technical': {
            'tone': '专业严谨',
            'focus': '技术深度',
            'keywords': ['架构', '性能', '工程化', '最佳实践']
        },
        'casual': {
            'tone': '轻松友好',
            'focus': '易用性',
            'keywords': ['简单', '好用', '实用', '有趣']
        },
        'marketing': {
            'tone': '营销导向',
            'focus': '商业价值',
            'keywords': ['爆款', '神器', '必备', '推荐']
        }
    }
    
    @classmethod
    def apply_style(cls, content: VideoMetadata, style: str) -> VideoMetadata:
        """应用特定风格到内容"""
        if style not in cls.STYLES:
            return content
        
        style_config = cls.STYLES[style]
        # 这里可以添加风格化处理逻辑
        return content


# 使用示例
def demo_content_analyzer():
    """演示内容分析器的使用"""
    # 创建测试项目数据
    from src.models.github_models import GitHubProject, GitHubProjectBase
    from datetime import datetime
    
    test_project = GitHubProject(
        id="test_project",
        url="https://github.com/test/user",
        name="AwesomeProject",
        full_name="test/AwesomeProject",
        description="一个非常棒的Python项目，具有高性能和易用性",
        language="Python",
        stars=1500,
        forks=200,
        watchers=300,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        owner="test",
        readme_content="""
        # AwesomeProject
        这是一个高性能的Python项目，专注于解决实际问题。
        ## 特性
        - 快速响应
        - 易于使用
        - 安全可靠
        ## 技术栈
        Python, FastAPI, Redis
        """,
        images=[]
    )
    
    # 分析内容
    analyzer = ContentAnalyzer()
    metadata = analyzer.analyze_project_content(test_project)
    
    print("生成的内容:")
    print(f"标题: {metadata.title}")
    print(f"副标题: {metadata.subtitle}")
    print(f"摘要: {metadata.summary}")
    print(f"标签: {', '.join(metadata.tags)}")
    print(f"AI生成: {metadata.ai_generated}")


if __name__ == "__main__":
    demo_content_analyzer()