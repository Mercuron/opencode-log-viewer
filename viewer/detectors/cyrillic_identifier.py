from __future__ import annotations

import re

from .base import Detection, SessionTrace, register

_BRACKET_IDENT = re.compile(r"\[([^\]]*[А-Яа-яЁё][^\]]*)\]")
_KEYWORD_IDENT = re.compile(r"\b(FROM|JOIN|INTO|UPDATE)\s+([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_.]*)", re.IGNORECASE)


def _has_cyrillic(s: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", s))


def find_cyrillic_identifiers(text: str) -> list[str]:
    found = set()
    for m in _BRACKET_IDENT.finditer(text):
        found.add(m.group(1))
    for m in _KEYWORD_IDENT.finditer(text):
        ident = m.group(2)
        if _has_cyrillic(ident):
            found.add(ident)
    return sorted(found)


@register
class CyrillicIdentifier:
    name = "cyrillic_identifier"

    def run(self, session: SessionTrace) -> list[Detection]:
        out = []
        for part in session.parts:
            candidates = " ".join(filter(None, [part.get("input_json"), part.get("output_text"), part.get("text")]))
            if not candidates:
                continue
            idents = find_cyrillic_identifiers(candidates)
            if idents:
                out.append(
                    Detection(
                        kind=self.name,
                        level="bad",
                        message=f"Кириллические идентификаторы в SQL: {', '.join(idents[:5])}",
                        evidence={"part_id": part["id"], "identifiers": idents},
                    )
                )
        return out
