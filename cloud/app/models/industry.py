from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IndustryPackRelease(Base):
    __tablename__ = "industry_pack_releases"

    path: Mapped[str] = mapped_column(String(128), primary_key=True)
    pack_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_yaml: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    l1_defaults_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
