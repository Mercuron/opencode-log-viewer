from __future__ import annotations

import json
import sqlite3

from viewer.importers.opencode_storage import import_storage
from viewer.retention import delete_session

SESSION_ID = "ses_import_test_1"
MESSAGE_ID = "msg_import_1"
PART_ID = "prt_import_1"
PROJECT_ID = "prj_import_1"


def _build_synthetic_sqlite(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT, name TEXT)")
    conn.execute(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY, project_id TEXT, parent_id TEXT, title TEXT, version TEXT,
            directory TEXT, time_created INTEGER, time_updated INTEGER
        )
        """
    )
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT)")
    conn.execute("CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT)")
    conn.execute("CREATE TABLE todo (session_id TEXT, content TEXT, status TEXT, priority TEXT, position INTEGER)")

    conn.execute("INSERT INTO project VALUES (?, ?, ?)", (PROJECT_ID, "/workspace/demo", "demo"))
    conn.execute(
        "INSERT INTO session VALUES (?, ?, NULL, ?, ?, ?, ?, ?)",
        (SESSION_ID, PROJECT_ID, "imported session", "0.1.0", "/workspace/demo", 1_770_000_000_000, 1_770_000_050_000),
    )
    message_data = {
        "id": MESSAGE_ID, "sessionID": SESSION_ID, "role": "assistant", "parentID": "msg_u",
        "modelID": "qwen2.5-coder-32b", "providerID": "llama-server", "mode": "build",
        "path": {"cwd": "/workspace/demo", "root": "/workspace/demo"}, "cost": 0,
        "time": {"created": 1_770_000_000_000, "completed": 1_770_000_040_000},
        "tokens": {"input": 1000, "output": 50, "reasoning": 0, "cache": {"read": 0, "write": 0}},
        "finish": "stop",
    }
    conn.execute("INSERT INTO message VALUES (?, ?, ?, ?)", (MESSAGE_ID, SESSION_ID, 1_770_000_000_000, json.dumps(message_data)))

    part_data = {
        "id": PART_ID, "sessionID": SESSION_ID, "messageID": MESSAGE_ID, "type": "tool",
        "callID": "call_import_1", "tool": "bash",
        "state": {"status": "completed", "input": {"command": "echo hi"}, "output": "hi", "title": "bash",
                  "metadata": {}, "time": {"start": 1_770_000_001_000, "end": 1_770_000_002_000}},
    }
    conn.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)", (PART_ID, MESSAGE_ID, SESSION_ID, 1_770_000_001_000, json.dumps(part_data)))

    conn.execute("INSERT INTO todo VALUES (?, ?, ?, ?, ?)", (SESSION_ID, "step one", "completed", "high", 0))
    conn.execute("INSERT INTO todo VALUES (?, ?, ?, ?, ?)", (SESSION_ID, "step two", "pending", "low", 1))
    conn.commit()
    conn.close()


def _build_synthetic_file_tree(root):
    session_dir = root / "session" / PROJECT_ID
    session_dir.mkdir(parents=True)
    (session_dir / f"{SESSION_ID}.json").write_text(json.dumps({
        "id": SESSION_ID, "projectID": PROJECT_ID, "directory": "/workspace/demo", "parentID": None,
        "title": "imported session", "version": "0.1.0",
        "time": {"created": 1_770_000_000_000, "updated": 1_770_000_050_000},
    }))

    message_dir = root / "message" / SESSION_ID
    message_dir.mkdir(parents=True)
    (message_dir / f"{MESSAGE_ID}.json").write_text(json.dumps({
        "id": MESSAGE_ID, "sessionID": SESSION_ID, "role": "assistant", "parentID": "msg_u",
        "modelID": "qwen2.5-coder-32b", "providerID": "llama-server", "mode": "build",
        "path": {"cwd": "/workspace/demo", "root": "/workspace/demo"}, "cost": 0,
        "time": {"created": 1_770_000_000_000, "completed": 1_770_000_040_000},
        "tokens": {"input": 1000, "output": 50, "reasoning": 0, "cache": {"read": 0, "write": 0}},
        "finish": "stop",
    }))

    part_dir = root / "part" / MESSAGE_ID
    part_dir.mkdir(parents=True)
    (part_dir / f"{PART_ID}.json").write_text(json.dumps({
        "id": PART_ID, "sessionID": SESSION_ID, "messageID": MESSAGE_ID, "type": "tool",
        "callID": "call_import_1", "tool": "bash",
        "state": {"status": "completed", "input": {"command": "echo hi"}, "output": "hi", "title": "bash",
                  "metadata": {}, "time": {"start": 1_770_000_001_000, "end": 1_770_000_002_000}},
    }))
    # Note: the file-tree layout (per real OpenCode migration code) has no
    # per-session todo file - todos only exist in the newer sqlite schema.
    # That asymmetry is real, not a test gap; the comparison below only
    # checks the fields both layouts can produce.


def _comparable(session_row: dict) -> dict:
    keys = ["title", "project", "directory", "model", "provider", "tool_calls", "tool_errors",
            "tokens_input", "tokens_output"]
    return {k: session_row[k] for k in keys}


def test_sqlite_and_file_layouts_produce_equivalent_normalized_session(conn, settings, tmp_path):
    db_path = tmp_path / "opencode.db"
    _build_synthetic_sqlite(str(db_path))
    import_storage(conn, settings, str(db_path), "sqlite-import-source")
    from_sqlite = dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (SESSION_ID,)).fetchone())

    delete_session(conn, SESSION_ID)

    file_root = tmp_path / "storage_tree"
    _build_synthetic_file_tree(file_root)
    import_storage(conn, settings, str(file_root), "files-import-source")
    from_files = dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (SESSION_ID,)).fetchone())

    assert _comparable(from_sqlite) == _comparable(from_files)


def test_import_marks_events_as_imported(conn, settings, tmp_path):
    db_path = tmp_path / "opencode.db"
    _build_synthetic_sqlite(str(db_path))
    result = import_storage(conn, settings, str(db_path), "sqlite-import-source")
    assert result.accepted > 0
    row = conn.execute("SELECT imported FROM events WHERE session_id = ? LIMIT 1", (SESSION_ID,)).fetchone()
    assert row["imported"] == 1
    session = conn.execute("SELECT imported FROM sessions WHERE id = ?", (SESSION_ID,)).fetchone()
    assert session["imported"] == 1
