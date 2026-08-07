"""Pydantic models for model configuration API."""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ModelProfileIn(BaseModel):
    id: str
    display_name: str
    provider: str = "deepseek"
    base_url: str
    model: str
    api_key: Optional[str] = None
    max_tokens: int = 8192
    temperature: float = 0.7
    enabled: bool = True


class ModelSectionIn(BaseModel):
    active_id: Optional[str] = None
    profiles: List[ModelProfileIn] = Field(default_factory=list)


class ModelsConfigIn(BaseModel):
    version: int = 1
    language: ModelSectionIn
    vision: ModelSectionIn


class ModelTestResponse(BaseModel):
    success: bool
    message: str
    reply: Optional[str] = None
