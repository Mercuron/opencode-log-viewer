from __future__ import annotations

from .base import Detection, SessionTrace, register


@register
class NoPromptCache:
    name = "no_prompt_cache"

    def run(self, session: SessionTrace) -> list[Detection]:
        total_input = sum(m["tokens_input"] or 0 for m in session.messages)
        total_cache_read = sum(m["tokens_cache_read"] or 0 for m in session.messages)
        if total_input > 50_000 and total_cache_read == 0:
            return [
                Detection(
                    kind=self.name,
                    level="bad",
                    message=f"cache_read=0 на всех шагах при суммарном input={total_input} токенов — промпт-кэш не работает или не пробрасывается",
                    evidence={"tokens_input": total_input},
                )
            ]
        return []
