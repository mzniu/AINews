"""配置管理模块"""
import os
from pathlib import Path
from typing import Any, Dict
import yaml
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Config:
    """配置类"""
    
    # 项目根目录
    ROOT_DIR = Path(__file__).parent.parent.parent
    
    # 数据目录
    DATA_DIR = ROOT_DIR / "data"
    RAW_DATA_DIR = DATA_DIR / "raw"
    PROCESSED_DATA_DIR = DATA_DIR / "processed"
    VIDEO_DIR = DATA_DIR / "videos"
    
    # DeepSeek配置
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    # 数据库配置
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/ainews.db")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # 爬虫配置
    CRAWLER_DELAY = int(os.getenv("CRAWLER_DELAY", "2"))
    CRAWLER_TIMEOUT = int(os.getenv("CRAWLER_TIMEOUT", "30"))
    USER_AGENT = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    # 视频配置
    VIDEO_RESOLUTION = os.getenv("VIDEO_RESOLUTION", "1080x1920")
    VIDEO_FORMAT = os.getenv("VIDEO_FORMAT", "mp4")
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/videos")
    
    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        for dir_path in [
            cls.DATA_DIR,
            cls.RAW_DATA_DIR,
            cls.PROCESSED_DATA_DIR,
            cls.VIDEO_DIR,
            cls.DATA_DIR / "logs"
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def load_sources(cls) -> Dict[str, Any]:
        """加载爬虫源配置"""
        config_file = cls.ROOT_DIR / "config" / "sources.yaml"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {"sources": []}

# 初始化目录
Config.ensure_dirs()
