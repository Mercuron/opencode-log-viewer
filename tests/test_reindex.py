from __future__ import annotations

from viewer.ingest import write_batch
from viewer.indexer import reindex_session

from .conftest import load_fixture_events


def _snapshot(conn, session_id):
    def rows(table):
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE session_id = ? ORDER BY id", (session_id,))]

    return {
        "session": dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()),
        "messages": [dict(r) for r in conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,))],
        "parts": [dict(r) for r in conn.execute("SELECT * FROM parts WHERE session_id = ? ORDER BY seq", (session_id,))],
        "todos": [{k: v for k, v in r.items() if k != "id"} for r in rows("todo_snapshots")],
        "detections": [
            {k: v for k, v in dict(r).items() if k != "id" and k != "created_at"}
            for r in conn.execute("SELECT * FROM detections WHERE session_id = ? ORDER BY kind, message", (session_id,))
        ],
    }


def test_reindex_from_raw_events_matches_realtime_ingest(conn, settings):
    events = load_fixture_events()
    result = write_batch(conn, events, settings)
    session_id = "ses_00fdbcb3affezdUs1su8KIvq3b"
    assert session_id in result.touched_sessions

    before = _snapshot(conn, session_id)

    conn.execute("BEGIN IMMEDIATE")
    reindex_session(conn, session_id)
    conn.execute("COMMIT")

    after = _snapshot(conn, session_id)
    assert before == after
