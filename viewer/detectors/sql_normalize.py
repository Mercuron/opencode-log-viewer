from __future__ import annotations

import json
import re

_COMMENT_LINE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'")
_NUMBER = re.compile(r"(?<![A-Za-z_])\d+(\.\d+)?")
_WS = re.compile(r"\s+")
_OPERATOR_SPACING = re.compile(r"\s*(<=|>=|<>|!=|=|<|>)\s*")


def normalize_sql_like(text: str) -> str:
    """Lowercases, strips SQL comments, collapses whitespace, canonicalizes
    spacing around comparison operators, and replaces string/numeric
    literals with `?` so a reformatted-but-equivalent query is recognized
    as the same call (required for repeated_tool_call)."""
    t = text.lower()
    t = _COMMENT_BLOCK.sub("", t)
    t = _COMMENT_LINE.sub("", t)
    t = _STRING_LITERAL.sub("?", t)
    t = _NUMBER.sub("?", t)
    t = _OPERATOR_SPACING.sub(r"\1", t)
    t = _WS.sub(" ", t).strip()
    return t


def normalize_call_signature(tool_name: str, input_json: str | None) -> str:
    if not input_json:
        return tool_name
    try:
        data = json.loads(input_json)
    except Exception:
        return f"{tool_name}:{normalize_sql_like(input_json)}"
    if isinstance(data, dict):
        parts = []
        for key in sorted(data.keys()):
            value = data[key]
            if isinstance(value, str):
                value = normalize_sql_like(value)
            parts.append(f"{key}={value}")
        return f"{tool_name}:" + "|".join(parts)
    return f"{tool_name}:{normalize_sql_like(str(data))}"
