from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"


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
