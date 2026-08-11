from __future__ import annotations

from collections import defaultdict

from .base import Detection, SessionTrace, register
from .sql_normalize import normalize_call_signature


@register
class RepeatedToolCall:
    name = "repeated_tool_call"

    def run(self, session: SessionTrace) -> list[Detection]:
        by_signature: dict[str, list[dict]] = defaultdict(list)
        for part in session.parts:
            if part["type"] != "tool":
                continue
            sig = normalize_call_signature(part["tool_name"] or "", part["input_json"])
            by_signature[sig].append(part)

        out = []
        for sig, calls in by_signature.items():
            if len(calls) >= 3:
                out.append(
                    Detection(
                        kind=self.name,
                        level="warn",
                        message=f"Инструмент «{calls[0]['tool_name']}» вызван {len(calls)} раз с эквивалентными аргументами",
                        evidence={"signature": sig, "part_ids": [c["id"] for c in calls]},
                    )
                )
        return out
