"""ORM models for playbook learning."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.engine import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class PlaybookVersion(Base):
    __tablename__ = "playbook_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    diff_json: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="candidate")
    trap_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PatternCard(Base):
    __tablename__ = "pattern_cards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    source_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    verdict_kind: Mapped[str] = mapped_column(String(32), default="")
    verdict_function: Mapped[str] = mapped_column(Text, default="")
    forbidden_transfers_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    card_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CopyAgentJob(Base):
    __tablename__ = "copy_agent_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), default="curate")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CopyDraft(Base):
    __tablename__ = "copy_drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    playbook_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body_json: Mapped[str] = mapped_column(Text, default="{}")
    fact_gate_json: Mapped[str] = mapped_column(Text, default="{}")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_after_select: Mapped[bool] = mapped_column(Boolean, default=False)
    selection_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CopyAgentSettings(Base):
    __tablename__ = "copy_agent_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    current_playbook_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    auto_uses_current_playbook: Mapped[bool] = mapped_column(Boolean, default=False)
    material_adaptive_playbook: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_material_adaptive_playbook: Mapped[bool] = mapped_column(Boolean, default=False)
    ranking_max_candidates: Mapped[int] = mapped_column(Integer, default=40)
