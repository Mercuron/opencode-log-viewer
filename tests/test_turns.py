from __future__ import annotations

from viewer.ingest import write_batch

from .conftest import load_fixture_events

SID = "ses_00fdbcb3affezdUs1su8KIvq3b"


def _envelope(seq, event_type, payload, event_id, base):
    return {
        "schema_version": 1, "event_id": event_id, "source_id": base["source_id"], "source_name": base["source_name"],
        "session_id": SID, "parent_session_id": None, "sequence": seq, "event_type": event_type,
        "event_time": None, "observed_at": "2026-08-10T15:00:00.000Z", "context": base["context"], "payload": payload,
    }


def test_pause_between_dialogue_turns_excluded_from_duration_and_unaccounted(conn, settings):
    events = load_fixture_events()
    base = events[0]
    write_batch(conn, events, settings)
    before = dict(conn.execute("SELECT duration_ms, unaccounted_ms FROM sessions WHERE id = ?", (SID,)).fetchone())

    pause_start = 1_770_000_023_000
    eighty_minutes = 80 * 60 * 1000
    extra = [
        _envelope(9001, "message.updated", {"info": {
            "id": "msg_user_002", "sessionID": SID, "role": "user",
            "time": {"created": pause_start + eighty_minutes},
        }}, "evt_turn2_user", base),
        _envelope(9002, "message.updated", {"info": {
            "id": "msg_asst_002", "sessionID": SID, "role": "assistant",
            "time": {"created": pause_start + eighty_minutes + 1000, "completed": pause_start + eighty_minutes + 6000},
            "modelID": "m", "providerID": "p", "mode": "build",
            "tokens": {"input": 100, "output": 10, "reasoning": 0, "cache": {"read": 0, "write": 0}},
        }}, "evt_turn2_asst", base),
    ]
    write_batch(conn, extra, settings)

    after = dict(conn.execute("SELECT duration_ms, unaccounted_ms FROM sessions WHERE id = ?", (SID,)).fetchone())

    # The second turn added ~5s of its own span - nowhere near the 80 minute
    # gap between the two turns. If the pause leaked in, this would be off
    # by ~4.8 million ms.
    added = after["duration_ms"] - before["duration_ms"]
    assert 4_000 <= added <= 10_000, f"expected ~5s added, got {added}ms - looks like the inter-turn pause leaked in"
    assert after["unaccounted_ms"] < before["unaccounted_ms"] + 10_000


def test_single_turn_session_duration_is_the_turns_own_span(conn, settings):
    """The original fixture session has exactly one dialogue turn: the user
    message (started_ms=...000500) through the assistant's completed_ms
    (...023000). duration_ms should be that span, anchored to the first
    message actually in the turn - not to session.created_at (which comes
    from a separate session.created event and can differ by the gap between
    "session record created" and "first message sent")."""
    events = load_fixture_events()
    write_batch(conn, events, settings)
    row = conn.execute("SELECT duration_ms FROM sessions WHERE id = ?", (SID,)).fetchone()
    assert row["duration_ms"] == 22500
