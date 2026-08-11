from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import UTC, datetime, timedelta

from .config import Settings

logger = logging.getLogger("viewer.retention")


def db_size_bytes(db_path: str) -> int:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = db_path + suffix
        if os.path.exists(p):
            total += os.path.getsize(p)
    return total


def delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        for table in ("detections", "todo_snapshots", "inference_spans", "parts", "messages", "events", "sessions"):
            column = "id" if table == "sessions" else "session_id"
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (session_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def apply_retention(conn: sqlite3.Connection, settings: Settings) -> list[str]:
    """Deletes whole sessions (events + every derived row) once either
    RETENTION_DAYS or RETENTION_MAX_GB is exceeded. Absence of any deletion
    policy is treated as a defect by the spec, so this always runs."""
    deleted: list[str] = []

    if settings.retention_days > 0:
        cutoff = (datetime.now(UTC) - timedelta(days=settings.retention_days)).isoformat()
        rows = conn.execute(
            "SELECT id FROM sessions WHERE created_at IS NOT NULL AND created_at < ?", (cutoff,)
        ).fetchall()
        for row in rows:
            delete_session(conn, row["id"])
            deleted.append(row["id"])

    if settings.retention_max_gb > 0:
        max_bytes = settings.retention_max_gb * 1024**3
        guard = 0
        while db_size_bytes(settings.db_path) > max_bytes and guard < 10_000:
            guard += 1
            oldest = conn.execute("SELECT id FROM sessions ORDER BY created_at ASC LIMIT 1").fetchone()
            if not oldest:
                break
            delete_session(conn, oldest["id"])
            deleted.append(oldest["id"])
        if deleted:
            conn.execute("VACUUM")

    if deleted:
        logger.info("retention: deleted %d session(s): %s", len(deleted), ", ".join(deleted[:20]))
    return deleted


async def retention_loop(conn: sqlite3.Connection, settings: Settings, interval_seconds: int = 86_400) -> None:
    while True:
        try:
            await asyncio.to_thread(apply_retention, conn, settings)
        except Exception:  # noqa: BLE001
            logger.exception("retention run failed")
        await asyncio.sleep(interval_seconds)
