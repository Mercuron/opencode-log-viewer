from __future__ import annotations

from .base import Detection, SessionTrace, register

THRESHOLD_MS = 10_000


@register
class SlowTool:
    name = "slow_tool"

    def run(self, session: SessionTrace) -> list[Detection]:
        out = []
        for part in session.parts:
            if part["type"] != "tool":
                continue
            duration = part["duration_ms"]
            if duration and duration > THRESHOLD_MS:
                out.append(
                    Detection(
                        kind=self.name,
                        level="info",
                        message=f"«{part['tool_name']}» выполнялся {duration / 1000:.1f} с",
                        evidence={"part_id": part["id"], "duration_ms": duration},
                    )
                )
        return out
