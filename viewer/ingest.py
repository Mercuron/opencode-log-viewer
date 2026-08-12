from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import Settings
from .indexer import reindex_session

REQUIRED_FIELDS = ["schema_version", "event_id", "source_id", "source_name", "sequence", "event_type", "observed_at", "context", "payload"]


@dataclass
class BatchResult:
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    touched_sessions: set[str] = field(default_factory=set)


def _validate(event: dict) -> str | None:
    for field_name in REQUIRED_FIELDS:
        if field_name not in event:
            return f"missing field: {field_name}"
    if event.get("schema_version") != 1:
        return f"unsupported schema_version: {event.get('schema_version')}"
    if not isinstance(event.get("payload"), dict):
        return "payload must be an object"
    return None


def _upsert_source(conn: sqlite3.Connection, event: dict, now: str) -> None:
    context = event.get("context") or {}
    conn.execute(
        """
        INSERT INTO sources (id, name, hostname, first_seen_at, last_seen_at, opencode_version, plugin_version)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            last_seen_at = excluded.last_seen_at,
            name = excluded.name,
            hostname = COALESCE(excluded.hostname, sources.hostname),
            opencode_version = COALESCE(excluded.opencode_version, sources.opencode_version),
            plugin_version = COALESCE(excluded.plugin_version, sources.plugin_version)
        """,
        (
            event["source_id"],
            event["source_name"],
            context.get("hostname"),
            now,
            now,
            context.get("opencode_version"),
            context.get("plugin_version"),
        ),
    )


def write_batch(conn: sqlite3.Connection, events: list[dict], settings: Settings, imported: bool = False) -> BatchResult:
    """Pure, synchronous write path shared by the HTTP ingest queue, the
    storage importer, and tests. Idempotent on event_id."""
    result = BatchResult()
    now = datetime.now(UTC).isoformat()
    touched_sessions: set[str] = set()

    conn.execute("BEGIN IMMEDIATE")
    try:
        for event in events:
            error = _validate(event)
            if error:
                result.rejected += 1
                result.errors.append({"event_id": event.get("event_id"), "error": error})
                continue

            # Payload is stored exactly as received - redaction is opt-in and applied only at
            # export time (see viewer/export.py::build_markdown), never at rest, per explicit
            # user decision that ingest-time redaction was silently destroying legitimate data
            # (GUIDs, long MCP tool names) with no way to recover it.
            payload = event["payload"]
            session_id = event.get("session_id")

            _upsert_source(conn, event, now)

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO events
                    (event_id, source_id, session_id, sequence, event_type, event_time,
                     observed_at, payload_json, context_json, truncated, original_size, imported, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["source_id"],
                    session_id,
                    event["sequence"],
                    event["event_type"],
                    event.get("event_time"),
                    event["observed_at"],
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(event.get("context") or {}, ensure_ascii=False),
                    1 if event.get("truncated") else 0,
                    event.get("original_size"),
                    1 if imported else 0,
                    now,
                ),
            )
            if cur.rowcount == 0:
                result.duplicates += 1
                continue
            result.accepted += 1
            if session_id:
                touched_sessions.add(session_id)

        for session_id in touched_sessions:
            reindex_session(conn, session_id)

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    result.touched_sessions = touched_sessions
    return result


class IngestWorker:
    """Single background writer (5.1): the HTTP handler enqueues and awaits
    a future instead of touching sqlite directly, guaranteeing sequential,
    single-writer access even though FastAPI may accept requests
    concurrently on the event loop."""

    def __init__(self, conn: sqlite3.Connection, settings: Settings, on_written=None):
        self._conn = conn
        self._settings = settings
        self._on_written = on_written
        self._queue: asyncio.Queue[tuple[list[dict], asyncio.Future]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def submit(self, events: list[dict]) -> BatchResult:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        await self._queue.put((events, fut))
        return await fut

    async def _run(self) -> None:
        while True:
            events, fut = await self._queue.get()
            try:
                result = await asyncio.to_thread(write_batch, self._conn, events, self._settings)
                if self._on_written:
                    for session_id in result.touched_sessions:
                        self._on_written(session_id)
                if not fut.cancelled():
                    fut.set_result(result)
            except Exception as exc:  # noqa: BLE001
                if not fut.cancelled():
                    fut.set_exception(exc)
