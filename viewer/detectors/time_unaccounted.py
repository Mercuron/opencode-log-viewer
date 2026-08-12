from __future__ import annotations

from .base import Detection, SessionTrace, register


@register
class TimeUnaccounted:
    name = "time_unaccounted"

    # Below this, percentages are noise: a live turn only a couple seconds old can
    # legitimately have a small, real gap that reads as a huge share of a tiny window
    # (see viewer/indexer.py's last_observed_ms handling, which covers most of this - this
    # is defense in depth for whatever it doesn't catch).
    MIN_DURATION_MS = 15_000

    def run(self, session: SessionTrace) -> list[Detection]:
        duration = session.session.get("duration_ms")
        unaccounted = session.session.get("unaccounted_ms")
        if not duration or duration < self.MIN_DURATION_MS:
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
