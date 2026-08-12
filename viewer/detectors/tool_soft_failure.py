from __future__ import annotations

import json

from .base import Detection, SessionTrace, register


def _looks_like_soft_failure(output_text: str) -> bool:
    try:
        data = json.loads(output_text)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict) and data.get("success") is False


@register
class ToolSoftFailure:
    """Catches the common MCP-style convention of a tool call that OpenCode
    itself reports as `status: completed` (the call didn't throw/time out)
    but whose own JSON body says `"success": false` - a failure the
    transport-level status can't see because it's opaque payload content,
    not a transport error. Separate from `tool_error` (real status=error)
    on purpose - conflating them would make a genuine transport failure
    harder to spot."""

    name = "tool_soft_failure"

    def run(self, session: SessionTrace) -> list[Detection]:
        out = []
        for part in session.parts:
            if part["type"] != "tool" or part.get("status") == "error":
                continue
            output_text = part.get("output_text")
            if not output_text or not _looks_like_soft_failure(output_text):
                continue
            out.append(
                Detection(
                    kind=self.name,
                    level="warn",
                    message=f"«{part['tool_name']}» вернул success=false в теле ответа, хотя статус вызова не error",
                    evidence={"part_id": part["id"]},
                )
            )
        return out
