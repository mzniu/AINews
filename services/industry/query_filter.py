"""SQLAlchemy helpers to scope list queries to the active L2 industry."""
from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy.orm import Query

from services.industry.profile import get_active_industry_id

ModelT = TypeVar("ModelT")


def apply_active_industry_filter(
    query: Query,
    model: type[ModelT],
    active_industry_id: str | None = None,
) -> Query:
    industry_id = active_industry_id or get_active_industry_id()
    column = getattr(model, "industry_id", None)
    if column is None:
        return query
    return query.filter(column == industry_id)


def resolve_list_industry_id(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    return get_active_industry_id()
