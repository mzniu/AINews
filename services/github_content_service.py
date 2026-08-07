"""
AI内容分析服务
基于项目内容自动生成视频标题、副标题、摘要和标签
"""
import json
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
        self.last_compliance: Optional[Dict] = None
        api_key = os.getenv('DEEPSEEK_API_KEY') or os.getenv('OPENAI_API_KEY')
        if api_key:
            self.client = OpenAI(
                api_key=api_key,
                base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
            )
        self.model = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
    
    def analyze_project_content(self, project: GitHubProject) -> VideoMetadata:
        """
        分析项目内容并生成视频元数据（单次 LLM JSON 调用，复用社交货币方法论 prompt）
        """
        if not self.client:
            logger.warning("未配置AI API密钥，使用默认内容生成")
            return self._generate_default_content(project)

        try:
            project_info = self._extract_project_info(project)
            return self._generate_content_via_json(project_info)
        except Exception as e:
            logger.error(f"AI内容生成失败: {e}")
            return self._generate_default_content(project)

    def _generate_content_via_json(self, info: Dict) -> VideoMetadata:
        """单次 LLM JSON 调用：复用 utils/content_methodology 的方法论 prompt，一次产出全部字段。"""
        from utils.content_methodology import build_methodology_prompt_section
        from utils.tags_normalizer import normalize_structured_tags
        from utils.summary_highlights import normalize_highlight_keywords_from_llm

        vmin = 120
        vmax = 400
        json_template = f"""
【输出 JSON 格式】（严格遵守，不要返回其他内容）
{{
  "target_audience": "推断的目标受众（≤12个汉字）",
  "praise_tags": ["夸赞标签1", "夸赞标签2", "夸赞标签3"],
  "traffic_hook": "流量钩子类型中文名（如「观众想看结果」），可空字符串",
  "main_line1": "主标题第一行（9~12汉字当量，必须以感叹词如突发！/炸裂！/爽了！等开头+话题引入，不含emoji）",
  "main_line2": "主标题第二行（9~12汉字当量，必须以「网友：」开头的尖锐锐评，可空字符串）",
  "sub_title": "副标题第一行（11~15汉字当量，轻观点收尾，不含emoji）",
  "sub_title2": "副标题第二行（11~15汉字当量，七种流量钩子之一，可空字符串）",
  "summary": "生成的摘要（40-50字，以「小牛说：」开头）",
  "tags": "#赛道标签 #垂直标签 #精准标签 #热点标签 #小牛说 #其他标签1 #其他标签2 #其他标签3 #其他标签4 #其他标签5",
  "voiceover_script": "口播稿全文（{vmin}~{vmax}字，以「小牛说：」开头）",
  "highlight_keywords": ["摘要中连续子串1", "子串2", "子串3"]
}}

【输入】
项目名称: {info['name']}
描述: {info['description']}
技术栈: {', '.join(info['tech_stack'])}
特点: {', '.join(info['features'])}
Star数: {info['stars']}
完整README内容:
{info['readme_content'][:3000]}
"""
        prompt = build_methodology_prompt_section(
            vmin=vmin, vmax=vmax, json_template=json_template
        )

        from utils.content_compliance import invoke_json_llm_with_compliance

        messages = [
            {
                "role": "system",
                "content": "你是顶级自媒体爆款文案大师，精通微信视频号的「社交货币 / 夸赞」方法论：通过高情商夸赞目标受众、帮用户立人设来触发社交裂变点赞；同时熟练掌握「制造悬念、列举数字、提出疑问、强调时效、引发争议（中立可讨论）、指向明确」六种辅助标题技法，能在方法论为主、技法为辅的前提下综合运用。主标题第一行必须以贴合正文的感叹词（如突发！、炸裂！、爽了！等）开头抓眼球。你的文案在合规前提下引发点赞与传播，信息密度高。绝对不使用任何emoji表情符号。请严格按照JSON格式返回结果。"
                + "我是小牛，一个专业的AI技术专家，对AI行业有深度的见解，请你根据项目信息为我生成标题、副标题、摘要、标签与口播稿。",
            },
            {"role": "user", "content": prompt},
        ]
        result, compliance = invoke_json_llm_with_compliance(
            client=self.client,
            model=self.model,
            messages=messages,
            temperature=0.85,
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192")),
            response_format={"type": "json_object"},
        )
        self.last_compliance = compliance.to_dict()

        main_line1 = (result.get('main_line1') or '').strip()
        main_line2 = (result.get('main_line2') or '').strip()
        sub_title = (result.get('sub_title') or '').strip()
        sub_title2 = (result.get('sub_title2') or '').strip()
        traffic_hook = (result.get('traffic_hook') or '').strip()
        title_two_lines = "\n".join([x for x in [main_line1, main_line2] if x])
        summary_text = (result.get("summary") or "").strip()
        voiceover_script = (result.get("voiceover_script") or "").strip()
        tags = normalize_structured_tags(result.get('tags', ''))
        highlight_keywords = normalize_highlight_keywords_from_llm(
            result.get("highlight_keywords"), summary_text
        )
        target_audience = (result.get("target_audience") or "").strip()
        raw_praise_tags = result.get("praise_tags") or []
        if isinstance(raw_praise_tags, str):
            raw_praise_tags = [t.strip() for t in raw_praise_tags.replace("，", ",").split(",") if t.strip()]
        praise_tags = [str(t).strip() for t in raw_praise_tags if str(t).strip()][:5]
        logger.success(
            f"GitHub内容生成成功 - 受众:{target_audience}, 夸赞:{praise_tags}, 钩子:{traffic_hook}, "
            f"L1:{main_line1}, L2:{main_line2}, 副1:{sub_title}, 副2:{sub_title2}, "
            f"摘要:{len(summary_text)}字, 口播:{len(voiceover_script)}字"
        )

        return VideoMetadata(
            title=format_main_title_two_lines(title_two_lines),
            subtitle=sub_title,
            subtitle2=sub_title2,
            summary=summary_text,
            tags=tags,
            ai_generated=True,
            confidence_score=0.9,
            target_audience=target_audience,
            praise_tags=praise_tags,
            traffic_hook=traffic_hook,
        )
    
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
            hook = "炸裂！星标狂飙的宝藏仓库"
        elif info['stars'] >= 5000:
            hook = "来了！社区都在盯的黑马"
        elif info['stars'] >= 1000:
            hook = "重磅！值得收藏的硬核开源"
        elif info['stars'] >= 500:
            hook = "绝了！最近很香的开源项目"
        else:
            hook = "爽了！挖到的宝藏级开源"

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