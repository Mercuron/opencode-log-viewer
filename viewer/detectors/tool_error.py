from __future__ import annotations

from .base import Detection, SessionTrace, register


@register
class ToolError:
    name = "tool_error"

    def run(self, session: SessionTrace) -> list[Detection]:
        out = []
        for part in session.parts:
            if part["type"] == "tool" and part.get("status") in ("error", "failed"):
                out.append(
                    Detection(
                        kind=self.name,
                        level="bad",
                        message=f"«{part['tool_name']}» завершился ошибкой: {(part.get('error') or '')[:200]}",
                        evidence={"part_id": part["id"]},
                    )
                )
        return out
