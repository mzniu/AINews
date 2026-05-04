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
from utils.title_units import format_main_title_two_lines

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
                title=format_main_title_two_lines(title),
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
            你的任务是基于项目信息生成「两行」中文主标题，用于竖屏/横屏视频首屏展示。
            创作时可综合运用视频号常用标题技法（择其二三即可）：制造悬念；列举数字（如Star数、版本、性能数字）；提出疑问；强调时效（若README确有更新/新规）；引发争议（技术选型中立讨论，不引战）；指向明确（如「后端开发者」「小白友好」）。

            版式硬性要求（必须遵守）：
            - 输出恰好两行，中间用换行符 \\n 分隔，不要加引号或序号。
            - 第一行：强话题性、吸睛、能引发好奇或讨论（可用疑问、反差、热词、惊叹），控制在约14个汉字以内；不要写完整项目全名，侧重「钩子」。
            - 第二行：点出项目名称或核心技术/价值补充，务必包含或明确指向项目名称「与第一行形成完整信息」；约14个汉字以内。
            - 两行加起来突出技术亮点与实用价值，用语真实不造谣。
            """
            
            user_prompt = f"""
            基于以下GitHub项目信息，生成两行中文主标题（第一行话题钩子，第二行项目名/亮点）：

            项目名称: {info['name']}
            描述: {info['description']}
            技术栈: {', '.join(info['tech_stack'])}
            特点: {', '.join(info['features'])}
            Star数: {info['stars']}
            完整README内容:
            {info['readme_content']}

            要求：
            1. 严格输出两行，用换行 \\n 分隔；第一行必须有话题性，第二行须包含或对应项目名称：{info['name']}
            2. 第一行像短视频爆款标题钩子（可含悬念、数字、疑问、受众指向），第二行落地到具体项目
            3. 可适度夸张但基于真实 README，不编造 Star 或功能
            4. 只返回两行标题，不要解释或其它内容
            """
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=80,
                temperature=0.75
            )
            
            title = response.choices[0].message.content.strip()
            # 统一换行，去掉模型可能加上的引号包裹
            title = title.replace("\r\n", "\n").strip().strip('"').strip("'")
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
            - 主标题可能为两行（第一行偏话题钩子、第二行偏项目名），副标题要从新角度补充，不要重复第一行钩子句
            - 可补充：数字（Star、性能）、悬念、时效（若确有）、明确受众，与主标题形成层次
            - 重点强调 Star、解决的痛点或应用场景
            - 长度控制在25-35个字符
            - 避免与主标题第二行同质化
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
            你是一位技术文档专家，擅长将复杂的GitHub项目信息写成适合口播/字幕的短摘要。

            摘要写作要求：
            - 长度控制在约120-160个字符（含标点）
            - 第一句必须是面向观众的「分享式」开场，例如「今天给大家分享一个宝藏项目」「给大家安利一个开源好项目」「给大家推荐一个我最近挖到的宝藏仓库」等同类表达，语气亲切自然；随后紧接项目名与一句核心价值。
            - 第二句起再展开：核心功能、解决什么问题、技术亮点（基于 README，不编造）；可自然加入具体数字、一句反问或「适合谁用」，增强视频号口播节奏
            - 语言口语化、通俗易懂，避免堆砌术语
            - 基于真实 README，保持准确性
            """
            
            user_prompt = f"""
            基于以下完整的GitHub项目 README，写一段中文摘要（口播稿风格）：

            项目名称: {info['name']}
            项目描述: {info['description']}
            技术栈: {', '.join(info['tech_stack'])}
            特点: {', '.join(info['features'])}
            Star数: {info['stars']}
            
            完整README内容:
            {full_readme}
            
            要求：
            1. 第一句必须是分享/安利式开场（类似「给大家分享一个宝藏项目」），并自然带出项目名 {info['name']}
            2. 后面几句说明做什么、解决什么问题、亮点是什么
            3. 直接返回一段连续摘要，不要小标题或列表
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
            你是一位社交媒体内容专家，擅长为技术项目创建精准的短视频标签体系。
            
            标签创建原则：
            - 严格输出 10 个标签，且顺序固定
            - 第1个：赛道标签，表示宏观领域/行业赛道
            - 第2个：垂直标签，表示细分方向/应用场景
            - 第3个：精准标签，表示项目名、产品名、技术名或最核心概念
            - 第4个：热点标签，表示当前传播热点、技术趋势或高关注话题
            - 第5个：个人IP标签，固定使用 #小牛说 或与内容强相关的 #小牛说AI
            - 第6～10个：其他补充标签，用于技术栈、受众、价值点、平台、场景等
            - 避免重复标签；每个标签都以 # 开头，用空格分隔
            """
            
            user_prompt = f"""
            为以下GitHub项目生成10个中文标签：
            
            项目名称: {info['name']}
            项目描述: {info['description']}
            技术栈: {', '.join(info['tech_stack'])}
            特点: {', '.join(info['features'])}
            Star数: {info['stars']}
            
            要求：
            1. 严格按顺序给出：1个赛道标签 + 1个垂直标签 + 1个精准标签 + 1个热点标签 + 1个个人IP标签 + 5个其他标签。
            2. 第5个个人IP标签优先固定为 #小牛说。
            3. 每个标签以 # 开头，用空格分隔，例如：#开源项目 #AI编程 #WorldMonitor #GitHub热门 #小牛说 #Python #监控工具 #开发者工具 #自动化 #效率工具。
            4. 只返回这一行标签，不要解释，不要编号，不要逗号。
            """
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=120,
                temperature=0.4
            )
            
            tags_text = response.choices[0].message.content.strip()
            tags = self._parse_hashtag_line(tags_text)
            if len(tags) < 10:
                defaults = self._generate_default_tags(info)
                for tag in defaults:
                    if tag not in tags:
                        tags.append(tag)
            has_ip_tag = '#小牛说' in tags or '#小牛说AI' in tags
            if not has_ip_tag:
                tags.insert(4, '#小牛说')
            elif len(tags) >= 5 and tags[4] not in ('#小牛说', '#小牛说AI'):
                ip_tag = '#小牛说' if '#小牛说' in tags else '#小牛说AI'
                tags = [tag for tag in tags if tag != ip_tag]
                tags.insert(4, ip_tag)
            return tags[:10]
            
        except Exception as e:
            logger.error(f"生成标签失败: {e}")
            return self._generate_default_tags(info)

    @staticmethod
    def _parse_hashtag_line(tags_text: str) -> List[str]:
        """解析模型返回的标签行，兼容空格、逗号、顿号与换行。"""
        raw_text = tags_text or ""
        hashtag_matches = re.findall(r"#[^\s,，、；;。.]+", raw_text)
        raw = raw_text.replace("，", " ").replace(",", " ").replace("、", " ")
        parts = hashtag_matches or re.split(r"\s+", raw.strip())
        tags: List[str] = []
        seen = set()
        for part in parts:
            tag = part.strip().strip("；;。.")
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = f"#{tag.lstrip('#')}"
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
        return tags
    
    def _generate_default_content(self, project: GitHubProject) -> VideoMetadata:
        """生成默认内容（当AI不可用时）"""
        info = self._extract_project_info(project)
        
        return VideoMetadata(
            title=format_main_title_two_lines(self._generate_default_title(info)),
            subtitle=self._generate_default_subtitle(info),
            summary=self._generate_default_summary(info),
            tags=self._generate_default_tags(info),
            ai_generated=False,
            confidence_score=0.7
        )
    
    def _generate_default_title(self, info: Dict) -> str:
        """无 API 时的默认两行标题：第一行话题钩子，第二行项目名。"""
        tech_part = f"[{info['language']}]" if info['language'] else ""

        if info['stars'] >= 10000:
            hook = "星标狂飙的宝藏仓库"
        elif info['stars'] >= 5000:
            hook = "社区都在盯的黑马项目"
        elif info['stars'] >= 1000:
            hook = "值得收藏的硬核开源"
        elif info['stars'] >= 500:
            hook = "最近很香的开源项目"
        else:
            hook = "挖到的宝藏级开源"

        # 两行：\n 便于后续与 index 一致拆行展示
        return f"{hook}\n{info['name']}{tech_part}"

    def _generate_default_subtitle(self, info: Dict) -> str:
        """无 AI 或未配置 API 时的默认副标题（与 _generate_default_subtitle_with_stars 一致）。"""
        return self._generate_default_subtitle_with_stars(info)

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
        """生成默认摘要（首句分享式开场）"""
        desc = info['description'] or f"这是一个优秀的{info['language']}项目"
        tech_text = f"，使用{', '.join(info['tech_stack'])}技术栈" if info['tech_stack'] else ""
        opener = "今天给大家分享一个宝藏项目"
        return f"{opener}「{info['name']}」。{desc}{tech_text}，值得关注和学习。"
    
    def _generate_default_tags(self, info: Dict) -> List[str]:
        """生成默认标签"""
        lane = '#开源项目'
        vertical = '#开发者工具'
        precise = f"#{info['name']}" if info.get('name') else '#GitHub项目'
        hot = '#GitHub热门' if info.get('stars', 0) >= 1000 else '#开源推荐'
        ip = '#小牛说'

        extras: List[str] = []
        if info.get('language'):
            extras.append(f"#{info['language']}")
        for tech in info.get('tech_stack') or []:
            extras.append(f"#{tech}")
        for feature in info.get('features') or []:
            extras.append(f"#{feature}")
        extras.extend(['#技术分享', '#效率工具', '#程序员', '#AI工具', '#项目推荐'])

        tags: List[str] = []
        seen = set()
        for tag in [lane, vertical, precise, hot, ip, *extras]:
            tag = tag if tag.startswith('#') else f'#{tag}'
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
            if len(tags) == 10:
                break
        return tags


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