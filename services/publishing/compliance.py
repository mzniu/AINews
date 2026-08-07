"""Pre-publish forbidden words validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from utils.forbidden_words import Violation, partition_violations, scan_content_fields


@dataclass
class PublishComplianceResult:
    ok: bool
    violations: list[Violation]


def validate_publish_payload(
    title: str,
    description: str | None,
    tags: Sequence[str],
) -> PublishComplianceResult:
    fields = {
        "main_line1": title,
        "sub_title": description or "",
        "tags": " ".join(str(item) for item in tags),
    }
    violations = scan_content_fields(fields)
    errors, _warnings = partition_violations(violations)
    return PublishComplianceResult(ok=not errors, violations=violations)
