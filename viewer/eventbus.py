from __future__ import annotations

import asyncio
from collections import defaultdict


class SessionEventBus:
    """In-process pub/sub used to drive the session SSE stream (6.4)."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[session_id].append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(session_id)
        if subs and q in subs:
            subs.remove(q)

    def publish(self, session_id: str) -> None:
        for q in self._subscribers.get(session_id, []):
            if not q.full():
                q.put_nowait(True)
