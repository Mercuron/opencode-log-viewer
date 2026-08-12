from __future__ import annotations

import json

from viewer.ingest import write_batch

from .conftest import load_fixture_events

SID = "ses_00fdbcb3affezdUs1su8KIvq3b"


def test_context_snapshot_event_is_stored_and_linked_to_last_message(conn, settings):
    events = load_fixture_events()
    base = events[0]
    snapshot_event = {
        "schema_version": 1, "event_id": "evt_ctx_snap_test", "source_id": base["source_id"],
        "source_name": base["source_name"], "session_id": SID, "parent_session_id": None,
        "sequence": 9500, "event_type": "context.snapshot", "event_time": None,
        "observed_at": "2026-08-10T14:00:22.500Z", "context": base["context"],
        "payload": {
            "systemChars": 500,
            "totalChars": 900,
            "breakdown": [{"role": "assistant", "messageID": "msg_asst_001", "parts": [{"type": "text", "chars": 400}]}],
        },
    }
    write_batch(conn, events + [snapshot_event], settings)

    row = conn.execute("SELECT * FROM context_snapshots WHERE session_id = ?", (SID,)).fetchone()
    assert row is not None
    assert row["message_id"] == "msg_asst_001"
    assert row["system_chars"] == 500
    assert row["total_chars"] == 900
    assert json.loads(row["breakdown_json"])[0]["role"] == "assistant"


def test_session_without_context_snapshot_has_no_rows(conn, settings):
    write_batch(conn, load_fixture_events(), settings)
    rows = conn.execute("SELECT * FROM context_snapshots WHERE session_id = ?", (SID,)).fetchall()
    assert rows == []


def test_tool_input_and_text_parts_get_token_estimates(conn, settings, client):
    """Tool call *arguments* and text/reasoning content used to contribute nothing to
    output_tokens_est/input_tokens_est - the "known from tool outputs" figure only ever
    looked at tool output text, which is most of why it undercounted real context usage so
    badly. Both should now carry an estimate."""
    events = load_fixture_events()
    write_batch(conn, events, settings)

    row = conn.execute(
        "SELECT input_tokens_est, output_tokens_est FROM parts WHERE type = 'tool' AND input_json IS NOT NULL LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["input_tokens_est"] is not None and row["input_tokens_est"] > 0

    text_row = conn.execute(
        "SELECT output_tokens_est FROM parts WHERE type IN ('text', 'reasoning') AND text IS NOT NULL LIMIT 1"
    ).fetchone()
    assert text_row is not None
    assert text_row["output_tokens_est"] is not None and text_row["output_tokens_est"] > 0

    assert client.post("/api/v1/auth/login", json={"password": "adminpw"}).status_code == 200
    detail = client.get(f"/api/v1/sessions/{SID}").json()
    attributed = detail["context_attribution"]
    assert any(a["input_tokens_est"] for a in attributed)


def test_context_snapshot_survives_reindex(conn, settings):
    from viewer.indexer import reindex_session

    events = load_fixture_events()
    base = events[0]
    snapshot_event = {
        "schema_version": 1, "event_id": "evt_ctx_snap_reindex", "source_id": base["source_id"],
        "source_name": base["source_name"], "session_id": SID, "parent_session_id": None,
        "sequence": 9501, "event_type": "context.snapshot", "event_time": None,
        "observed_at": "2026-08-10T14:00:22.600Z", "context": base["context"],
        "payload": {"systemChars": 10, "totalChars": 20, "breakdown": []},
    }
    write_batch(conn, events + [snapshot_event], settings)

    conn.execute("BEGIN IMMEDIATE")
    reindex_session(conn, SID)
    conn.execute("COMMIT")

    rows = conn.execute("SELECT * FROM context_snapshots WHERE session_id = ?", (SID,)).fetchall()
    assert len(rows) == 1
