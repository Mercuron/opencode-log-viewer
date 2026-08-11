from __future__ import annotations

import re

_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")


def estimate_tokens(text: str | None) -> int:
    """Rough length-based token estimate, corrected for Cyrillic (heavier per
    token than Latin in most BPE vocabularies). Always an approximation -
    callers must present it with an "≈" prefix per 5.5."""
    if not text:
        return 0
    cyrillic = len(_CYRILLIC_RE.findall(text))
    total = len(text)
    latin_ish = total - cyrillic
    return round(latin_ish / 4.0 + cyrillic / 2.3)
