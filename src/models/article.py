"""文章数据模型"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field


class Article(BaseModel):
    """文章数据模型"""
    
    id: Optional[str] = None
    title: str
    url: HttpUrl
    source: str
    author: Optional[str] = None
    publish_time: Optional[datetime] = None
    content: str
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    crawl_time: datetime = Field(default_factory=datetime.now)
    status: str = "pending"  # pending, processed, published
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
    
    def to_dict(self):
        """转换为字典"""
        return self.model_dump(mode='json')
