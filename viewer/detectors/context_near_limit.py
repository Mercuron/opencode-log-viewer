from __future__ import annotations

from .base import Detection, SessionTrace, register

# Best-effort context window table for common models. Unknown models are
# skipped rather than guessed (no invented precision).
KNOWN_CONTEXT_WINDOWS = {
    "qwen2.5-coder-32b": 128_000,
    "qwen2.5-coder": 128_000,
    "gpt-4o": 128_000,
    "gpt-4.1": 1_000_000,
    "claude-sonnet-5": 200_000,
    "claude-opus-5": 200_000,
    "claude-haiku-4-5": 200_000,
    "deepseek-coder-v2": 128_000,
    "llama-3.1-70b": 128_000,
}


@register
class ContextNearLimit:
    name = "context_near_limit"

    def run(self, session: SessionTrace) -> list[Detection]:
        model = (session.session.get("model") or "").lower()
        limit = next((v for k, v in KNOWN_CONTEXT_WINDOWS.items() if k in model), None)
        if not limit:
            return []
        out = []
        for m in session.messages:
            tokens_input = m.get("tokens_input") or 0
            if tokens_input > 0.8 * limit:
                out.append(
                    Detection(
                        kind=self.name,
                        level="warn",
                        message=f"Сообщение #{m['seq']}: input={tokens_input} — больше 80% контекстного окна модели ({limit})",
                        evidence={"message_id": m["id"], "tokens_input": tokens_input, "limit": limit},
                    )
                )
        return out
