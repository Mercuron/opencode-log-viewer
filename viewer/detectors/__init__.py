from __future__ import annotations

import importlib
import json
import pkgutil
import sqlite3
from datetime import UTC, datetime

from .base import Detection, SessionTrace, registered_detectors

_AUTOLOADED = False


def _autoload() -> None:
    global _AUTOLOADED
    if _AUTOLOADED:
        return
    package = importlib.import_module(__name__)
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if module_name in ("base", "sql_normalize"):
            continue
        importlib.import_module(f"{__name__}.{module_name}")
    _AUTOLOADED = True


def _load_trace(conn: sqlite3.Connection, session_id: str) -> SessionTrace | None:
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        return None
    messages = conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)).fetchall()
    parts = conn.execute("SELECT * FROM parts WHERE session_id = ? ORDER BY seq", (session_id,)).fetchall()
    todos = conn.execute("SELECT * FROM todo_snapshots WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
    return SessionTrace(
        session=dict(session),
        messages=[dict(m) for m in messages],
        parts=[dict(p) for p in parts],
        todo_snapshots=[dict(t) for t in todos],
    )


def run_detectors(conn: sqlite3.Connection, session_id: str) -> list[Detection]:
    _autoload()
    trace = _load_trace(conn, session_id)
    conn.execute("DELETE FROM detections WHERE session_id = ?", (session_id,))
    if trace is None:
        return []
    now = datetime.now(UTC).isoformat()
    results: list[Detection] = []
    for detector in registered_detectors():
        try:
            results.extend(detector.run(trace))
        except Exception as exc:  # noqa: BLE001 - one bad detector must not break indexing
            results.append(Detection(kind=getattr(detector, "name", "unknown"), level="info", message=f"detector failed: {exc}"))
    for d in results:
        conn.execute(
            "INSERT INTO detections (session_id, kind, level, message, evidence_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, d.kind, d.level, d.message, json.dumps(d.evidence, ensure_ascii=False), now),
        )
    return results
