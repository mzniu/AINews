"""ORM for LLM/VL token usage events."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.engine import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class LlmTokenUsageEvent(Base):
    __tablename__ = "llm_token_usage_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    task: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
