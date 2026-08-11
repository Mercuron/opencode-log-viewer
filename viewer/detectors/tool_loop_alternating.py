from __future__ import annotations

from .base import Detection, SessionTrace, register
from .sql_normalize import normalize_call_signature


@register
class ToolLoopAlternating:
    name = "tool_loop_alternating"

    def run(self, session: SessionTrace) -> list[Detection]:
        tool_parts = sorted(
            (p for p in session.parts if p["type"] == "tool"),
            key=lambda p: p["seq"],
        )
        sequence = [normalize_call_signature(p["tool_name"] or "", p["input_json"]) for p in tool_parts]

        counts: dict[str, int] = {}
        for i in range(len(sequence) - 1):
            a, b = sequence[i], sequence[i + 1]
            if a != b and i + 2 < len(sequence) and sequence[i + 2] == a:
                pair = tuple(sorted((a, b)))
                counts[pair] = counts.get(pair, 0) + 1

        out = []
        for pair, count in counts.items():
            total_repeats = count * 2
            if total_repeats >= 6:
                out.append(
                    Detection(
                        kind=self.name,
                        level="warn",
                        message=f"Обнаружено чередование двух вызовов ({total_repeats} повторов суммарно) — похоже на цикл",
                        evidence={"signatures": list(pair), "repeats": total_repeats},
                    )
                )
        return out
