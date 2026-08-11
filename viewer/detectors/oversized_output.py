from __future__ import annotations

from .base import Detection, SessionTrace, register

THRESHOLD_TOKENS = 20_000


@register
class OversizedOutput:
    name = "oversized_output"

    def run(self, session: SessionTrace) -> list[Detection]:
        out = []
        for part in session.parts:
            est = part.get("output_tokens_est")
            if est and est > THRESHOLD_TOKENS:
                out.append(
                    Detection(
                        kind=self.name,
                        level="warn",
                        message=f"Вывод «{part['tool_name'] or part['type']}» ≈{est} токенов — крупнейший потребитель контекста",
                        evidence={"part_id": part["id"], "output_tokens_est": est},
                    )
                )
        return out
