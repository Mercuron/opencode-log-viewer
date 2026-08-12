from __future__ import annotations

import re
import sqlite3
from typing import Any

REDACTED = "[REDACTED]"


def load_patterns(conn: sqlite3.Connection) -> list[re.Pattern]:
    """The `redact_patterns` table (seeded once from REDACT_PATTERNS at
    first migration, see migrations/0003_*.sql) is the live source of truth
    from here on - editable from Settings without a restart. A pattern that
    fails to compile (e.g. edited badly outside the UI) is skipped rather
    than crashing ingestion for everyone."""
    patterns = []
    for row in conn.execute("SELECT pattern FROM redact_patterns WHERE enabled = 1"):
        try:
            patterns.append(re.compile(row["pattern"]))
        except re.error:
            continue
    return patterns


def _redact_string(value: str, patterns: list[re.Pattern]) -> str:
    for pattern in patterns:
        value = pattern.sub(REDACTED, value)
    return value


def redact_value(value: Any, patterns: list[re.Pattern]) -> Any:
    if not patterns:
        return value
    if isinstance(value, str):
        return _redact_string(value, patterns)
    if isinstance(value, dict):
        return {k: redact_value(v, patterns) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, patterns) for v in value]
    return value
