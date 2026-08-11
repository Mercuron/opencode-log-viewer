from __future__ import annotations

from .base import Detection, SessionTrace, register


@register
class TimeUnaccounted:
    name = "time_unaccounted"

    def run(self, session: SessionTrace) -> list[Detection]:
        duration = session.session.get("duration_ms")
        unaccounted = session.session.get("unaccounted_ms")
        if not duration:
            return []
        share = (unaccounted or 0) / duration
        if share > 0.5:
            return [
                Detection(
                    kind=self.name,
                    level="warn",
                    message=f"{round(share * 100)}% времени сессии не покрыто событиями с известными границами",
                    evidence={"duration_ms": duration, "unaccounted_ms": unaccounted},
                )
            ]
        return []
