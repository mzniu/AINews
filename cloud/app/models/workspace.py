from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), default="personal")
    name: Mapped[str] = mapped_column(String(128), default="Personal")
    owner_usercenter_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("usercenter_accounts.usercenter_user_id"),
        index=True,
    )
    active_industry_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry_selected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
