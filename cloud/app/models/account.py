from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UsercenterAccount(Base):
    __tablename__ = "usercenter_accounts"

    usercenter_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
