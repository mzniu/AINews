"""Industry vertical identifiers (M0 preset L2 paths)."""
from __future__ import annotations

import re

DEFAULT_INDUSTRY_ID = "tech/ai"

INDUSTRY_ID_PATTERN = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+$")


def is_valid_industry_id(value: str) -> bool:
    return bool(value and INDUSTRY_ID_PATTERN.fullmatch(value.strip()))
