from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..ingest import write_batch, BatchResult


def _event_id(*parts: str) -> str:
    return "evt_import_" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def _iso(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _context(source_name: str, project: str | None, directory: str | None) -> dict:
    return {
        "project": project,
        "directory": directory,
        "worktree": directory,
        "hostname": "import",
        "opencode_version": None,
        "plugin_version": "import",
        "inference_base_url": None,
    }


def _envelope(
    *,
    source_name: str,
    source_id: str,
    session_id: str | None,
    parent_session_id: str | None,
    sequence: int,
    event_type: str,
    event_time_ms: int | None,
    payload: dict,
    context: dict,
) -> dict:
    return {
        "schema_version": 1,
        "event_id": _event_id(source_name, event_type, session_id or "", str(sequence)),
        "source_id": source_id,
        "source_name": source_name,
        "session_id": session_id,
        "parent_session_id": parent_session_id,
        "sequence": sequence,
        "event_type": event_type,
        "event_time": _iso(event_time_ms),
        "observed_at": datetime.now(UTC).isoformat(),
        "context": context,
        "payload": payload,
    }


def detect_layout(root: Path) -> str:
    if root.is_file() and root.suffix in (".db", ".sqlite", ".sqlite3"):
        return "sqlite"
    for candidate in (root / "opencode.db", root / "storage" / "opencode.db"):
        if candidate.exists():
            return "sqlite"
    for candidate in (root / "session", root / "storage" / "session"):
        if candidate.is_dir():
            return "files"
    raise ValueError(f"unrecognized OpenCode storage layout at {root}")


def _sqlite_db_path(root: Path) -> Path:
    if root.is_file():
        return root
    for candidate in (root / "opencode.db", root / "storage" / "opencode.db"):
        if candidate.exists():
            return candidate
    raise ValueError("opencode.db not found")


def _events_from_sqlite(db_path: Path, source_name: str, source_id: str) -> list[dict]:
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    events: list[dict] = []
    seq_by_session: dict[str, int] = {}

    def next_seq(session_id: str) -> int:
        seq_by_session[session_id] = seq_by_session.get(session_id, 0) + 1
        return seq_by_session[session_id]

    projects = {row["id"]: dict(row) for row in src.execute("SELECT * FROM project")}

    for row in src.execute("SELECT * FROM session ORDER BY time_created ASC"):
        session = dict(row)
        sid = session["id"]
        project = projects.get(session["project_id"], {})
        # Use project_id consistently (not project.name) so this matches
        # the file-tree importer, which only has the project_id directory
        # name available - no separate project.json is guaranteed to exist.
        ctx = _context(source_name, session["project_id"], session.get("directory") or project.get("worktree"))
        payload = {
            "info": {
                "id": sid,
                "projectID": session["project_id"],
                "directory": session.get("directory") or project.get("worktree"),
                "parentID": session.get("parent_id"),
                "title": session.get("title"),
                "version": session.get("version") or "",
                "time": {"created": session["time_created"], "updated": session["time_updated"]},
            }
        }
        events.append(
            _envelope(
                source_name=source_name, source_id=source_id, session_id=sid, parent_session_id=session.get("parent_id"),
                sequence=next_seq(sid), event_type="session.created", event_time_ms=session["time_created"],
                payload=payload, context=ctx,
            )
        )

    for row in src.execute("SELECT * FROM message ORDER BY time_created ASC"):
        data = json.loads(row["data"])
        sid = row["session_id"]
        ctx = _context(source_name, None, None)
        events.append(
            _envelope(
                source_name=source_name, source_id=source_id, session_id=sid, parent_session_id=None,
                sequence=next_seq(sid), event_type="message.updated", event_time_ms=row["time_created"],
                payload={"info": data}, context=ctx,
            )
        )

    for row in src.execute("SELECT * FROM part ORDER BY time_created ASC"):
        data = json.loads(row["data"])
        sid = row["session_id"]
        ctx = _context(source_name, None, None)
        events.append(
            _envelope(
                source_name=source_name, source_id=source_id, session_id=sid, parent_session_id=None,
                sequence=next_seq(sid), event_type="message.part.updated", event_time_ms=row["time_created"],
                payload={"part": data}, context=ctx,
            )
        )

    todos_by_session: dict[str, list] = {}
    for row in src.execute("SELECT * FROM todo ORDER BY session_id, position ASC"):
        todos_by_session.setdefault(row["session_id"], []).append(
            {"content": row["content"], "status": row["status"], "priority": row["priority"]}
        )
    for sid, todos in todos_by_session.items():
        ctx = _context(source_name, None, None)
        events.append(
            _envelope(
                source_name=source_name, source_id=source_id, session_id=sid, parent_session_id=None,
                sequence=next_seq(sid), event_type="todo.updated", event_time_ms=None,
                payload={"sessionID": sid, "todos": todos}, context=ctx,
            )
        )

    src.close()
    events.sort(key=lambda e: (e["session_id"] or "", e["sequence"]))
    return events


def _events_from_files(root: Path, source_name: str, source_id: str) -> list[dict]:
    base = root / "storage" if (root / "storage" / "session").is_dir() else root
    events: list[dict] = []
    seq_by_session: dict[str, int] = {}

    def next_seq(session_id: str) -> int:
        seq_by_session[session_id] = seq_by_session.get(session_id, 0) + 1
        return seq_by_session[session_id]

    session_dir = base / "session"
    if session_dir.is_dir():
        for project_dir in session_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for f in project_dir.glob("*.json"):
                info = json.loads(f.read_text())
                sid = info.get("id") or f.stem
                ctx = _context(source_name, project_dir.name, info.get("directory"))
                events.append(
                    _envelope(
                        source_name=source_name, source_id=source_id, session_id=sid,
                        parent_session_id=info.get("parentID"), sequence=next_seq(sid),
                        event_type="session.created", event_time_ms=(info.get("time") or {}).get("created"),
                        payload={"info": info}, context=ctx,
                    )
                )

    message_dir = base / "message"
    if message_dir.is_dir():
        for session_subdir in message_dir.iterdir():
            if not session_subdir.is_dir():
                continue
            sid = session_subdir.name
            ctx = _context(source_name, None, None)
            for f in session_subdir.glob("*.json"):
                info = json.loads(f.read_text())
                events.append(
                    _envelope(
                        source_name=source_name, source_id=source_id, session_id=sid, parent_session_id=None,
                        sequence=next_seq(sid), event_type="message.updated",
                        event_time_ms=(info.get("time") or {}).get("created"), payload={"info": info}, context=ctx,
                    )
                )

    part_dir = base / "part"
    if part_dir.is_dir():
        for message_subdir in part_dir.iterdir():
            if not message_subdir.is_dir():
                continue
            for f in message_subdir.glob("*.json"):
                part = json.loads(f.read_text())
                sid = part.get("sessionID")
                if not sid:
                    continue
                ctx = _context(source_name, None, None)
                events.append(
                    _envelope(
                        source_name=source_name, source_id=source_id, session_id=sid, parent_session_id=None,
                        sequence=next_seq(sid), event_type="message.part.updated",
                        event_time_ms=(part.get("time") or {}).get("start"), payload={"part": part}, context=ctx,
                    )
                )

    events.sort(key=lambda e: (e["session_id"] or "", e["sequence"]))
    return events


def import_storage(conn: sqlite3.Connection, settings: Settings, path: str, source_name: str) -> BatchResult:
    root = Path(path)
    source_id = hashlib.sha256(f"import-{source_name}".encode()).hexdigest()[:16]
    layout = detect_layout(root)
    if layout == "sqlite":
        events = _events_from_sqlite(_sqlite_db_path(root), source_name, source_id)
    else:
        events = _events_from_files(root, source_name, source_id)
    if not events:
        return BatchResult()
    return write_batch(conn, events, settings, imported=True)
