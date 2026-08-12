from __future__ import annotations

import json

from viewer.ingest import write_batch

from .conftest import load_fixture_events

SESSION_ID = "ses_00fdbcb3affezdUs1su8KIvq3b"
SUBAGENT_SESSION_ID = "ses_00fdbcb3affezdUs1su8KIvq3c"


def _login(client):
    r = client.post("/api/v1/auth/login", json={"password": "adminpw"})
    assert r.status_code == 200


def test_rename_source_persists_and_survives_reindex(client, conn):
    events = load_fixture_events()
    headers = {"Authorization": "Bearer s3cret"}
    client.post("/api/v1/events/batch", json={"events": events}, headers=headers)
    _login(client)

    source_id = client.get("/api/v1/sources").json()[0]["id"]
    r = client.patch(f"/api/v1/sources/{source_id}", json={"display_name": "MVK CodeQA prod"})
    assert r.status_code == 200

    # Re-ingesting (which triggers reindex of touched sessions) must not wipe the label.
    client.post("/api/v1/events/batch", json={"events": events}, headers=headers)
    source = client.get("/api/v1/sources").json()[0]
    assert source["display_name"] == "MVK CodeQA prod"
    assert source["name"] == "mvk-codeqa"


def test_rename_missing_source_is_404(client):
    _login(client)
    r = client.patch("/api/v1/sources/does-not-exist", json={"display_name": "x"})
    assert r.status_code == 404


def test_session_notes_persist_and_survive_reindex(client, conn):
    events = load_fixture_events()
    headers = {"Authorization": "Bearer s3cret"}
    client.post("/api/v1/events/batch", json={"events": events}, headers=headers)
    _login(client)

    r = client.patch(f"/api/v1/sessions/{SESSION_ID}", json={"notes": "проверить связь с MSSQL"})
    assert r.status_code == 200

    client.post("/api/v1/events/batch", json={"events": events}, headers=headers)
    detail = client.get(f"/api/v1/sessions/{SESSION_ID}").json()
    assert detail["session"]["notes"] == "проверить связь с MSSQL"


def test_update_missing_session_is_404(client):
    _login(client)
    r = client.patch("/api/v1/sessions/does-not-exist", json={"notes": "x"})
    assert r.status_code == 404


def test_unaccounted_ms_accounts_for_message_windows_not_just_parts(conn, settings):
    """Regression guard for the waterfall/unaccounted_ms bug: message-level
    [started_at, completed_at] windows must count as covered time, not just
    the handful of parts that happen to carry explicit timing."""
    write_batch(conn, load_fixture_events(), settings)
    row = conn.execute(
        "SELECT duration_ms, unaccounted_ms FROM sessions WHERE id = ?", (SESSION_ID,)
    ).fetchone()
    assert row["duration_ms"] > 0
    # Before the fix this fixture showed ~10% unaccounted from part-only
    # coverage; message windows should close almost all of that gap.
    assert row["unaccounted_ms"] / row["duration_ms"] < 0.1


def test_subtask_part_links_to_matching_child_session(conn, settings):
    events = load_fixture_events()
    subtask_event = {
        "schema_version": 1,
        "event_id": "evt_test_subtask_1",
        "source_id": events[0]["source_id"],
        "source_name": events[0]["source_name"],
        "session_id": SESSION_ID,
        "parent_session_id": None,
        "sequence": 9001,
        "event_type": "message.part.updated",
        "event_time": None,
        "observed_at": "2026-08-10T14:00:20.000Z",
        "context": events[0]["context"],
        "payload": {
            "part": {
                "id": "prt_subtask_1",
                "sessionID": SESSION_ID,
                "messageID": "msg_asst_001",
                "type": "subtask",
                "agent": "scout-db",
                "prompt": "find all references to MVK_WATER-DEV",
                "description": "scout-db: locate MVK_WATER-DEV usages",
            }
        },
    }
    # The child session this subtask spawned - same shape a real
    # session.created for a subagent would have (parentID + agent name
    # showing up via its own assistant messages' mode field).
    child_created = {
        "schema_version": 1,
        "event_id": "evt_test_child_created",
        "source_id": events[0]["source_id"],
        "source_name": events[0]["source_name"],
        "session_id": SUBAGENT_SESSION_ID,
        "parent_session_id": SESSION_ID,
        "sequence": 1,
        "event_type": "session.created",
        "event_time": None,
        "observed_at": "2026-08-10T14:00:21.000Z",
        "context": events[0]["context"],
        "payload": {"info": {"id": SUBAGENT_SESSION_ID, "parentID": SESSION_ID, "title": "scout-db run"}},
    }
    child_message = {
        "schema_version": 1,
        "event_id": "evt_test_child_message",
        "source_id": events[0]["source_id"],
        "source_name": events[0]["source_name"],
        "session_id": SUBAGENT_SESSION_ID,
        "parent_session_id": SESSION_ID,
        "sequence": 2,
        "event_type": "message.updated",
        "event_time": None,
        "observed_at": "2026-08-10T14:00:22.000Z",
        "context": events[0]["context"],
        "payload": {
            "info": {
                "id": "msg_scout_1",
                "sessionID": SUBAGENT_SESSION_ID,
                "role": "assistant",
                "modelID": "qwen36-codeqa-64k:latest",
                "providerID": "local",
                "mode": "scout-db",
                "time": {"created": 1770000030000, "completed": 1770000035000},
            }
        },
    }

    write_batch(conn, events + [subtask_event, child_created, child_message], settings)

    part = conn.execute("SELECT * FROM parts WHERE id = 'prt_subtask_1'").fetchone()
    assert part["type"] == "subtask"
    assert part["tool_name"] == "task:scout-db"
    assert json.loads(part["input_json"])["agent"] == "scout-db"

    child = conn.execute("SELECT agent FROM sessions WHERE id = ?", (SUBAGENT_SESSION_ID,)).fetchone()
    assert child["agent"] == "scout-db"


def test_session_detail_api_exposes_heuristic_link_to_child_session(client):
    events = load_fixture_events()
    base_ctx = events[0]["context"]
    base_source = (events[0]["source_id"], events[0]["source_name"])

    def envelope(seq, session_id, event_type, payload, event_id):
        return {
            "schema_version": 1, "event_id": event_id, "source_id": base_source[0], "source_name": base_source[1],
            "session_id": session_id, "parent_session_id": None, "sequence": seq, "event_type": event_type,
            "event_time": None, "observed_at": "2026-08-10T14:00:20.000Z", "context": base_ctx, "payload": payload,
        }

    extra = [
        envelope(9001, SESSION_ID, "message.part.updated", {"part": {
            "id": "prt_subtask_api", "sessionID": SESSION_ID, "messageID": "msg_asst_001", "type": "subtask",
            "agent": "scout-db", "prompt": "p", "description": "d",
        }}, "evt_api_subtask"),
        envelope(1, SUBAGENT_SESSION_ID, "session.created", {"info": {"id": SUBAGENT_SESSION_ID, "parentID": SESSION_ID, "title": "scout"}}, "evt_api_child_created"),
        envelope(2, SUBAGENT_SESSION_ID, "message.updated", {"info": {
            "id": "msg_scout_api", "sessionID": SUBAGENT_SESSION_ID, "role": "assistant", "modelID": "m",
            "providerID": "local", "mode": "scout-db", "time": {"created": 1, "completed": 2},
        }}, "evt_api_child_message"),
    ]

    headers = {"Authorization": "Bearer s3cret"}
    client.post("/api/v1/events/batch", json={"events": events + extra}, headers=headers)
    _login(client)

    detail = client.get(f"/api/v1/sessions/{SESSION_ID}").json()
    subtask_parts = [p for p in detail["parts"] if p["type"] == "subtask"]
    assert len(subtask_parts) == 1
    assert subtask_parts[0]["linked_session_id"] == SUBAGENT_SESSION_ID
    assert subtask_parts[0]["linked_session_match"] == "heuristic"
