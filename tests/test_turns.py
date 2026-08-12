from __future__ import annotations

from datetime import UTC, datetime

from viewer.ingest import write_batch

from .conftest import load_fixture_events

SID = "ses_00fdbcb3affezdUs1su8KIvq3b"


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _envelope(seq, event_type, payload, event_id, base, observed_ms: int | None = None):
    return {
        "schema_version": 1, "event_id": event_id, "source_id": base["source_id"], "source_name": base["source_name"],
        "session_id": SID, "parent_session_id": None, "sequence": seq, "event_type": event_type,
        "event_time": None,
        "observed_at": _iso(observed_ms) if observed_ms is not None else "2026-08-10T15:00:00.000Z",
        "context": base["context"], "payload": payload,
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


def test_live_turn_with_no_completed_message_is_not_100pct_unaccounted(conn, settings):
    """While a turn's only assistant message is still running (started, no completed_ms
    yet - e.g. a long `task` tool call in flight), the turn used to freeze at a near-zero
    span (end = the message's own start) and any small coverage gap inside that tiny window
    read as ~100% unaccounted. Now the turn stretches to the latest observed_at we actually
    have for the session, and the open message counts as covered up to that point too - so a
    long-running-but-clearly-busy turn doesn't look abandoned."""
    events = load_fixture_events()
    base = events[0]
    write_batch(conn, events, settings)

    turn_start = 1_770_000_100_000
    five_minutes = 5 * 60 * 1000
    write_batch(
        conn,
        [
            _envelope(9101, "message.updated", {"info": {
                "id": "msg_user_003", "sessionID": SID, "role": "user",
                "time": {"created": turn_start},
            }}, "evt_turn3_user", base, observed_ms=turn_start),
            _envelope(9102, "message.updated", {"info": {
                "id": "msg_asst_003", "sessionID": SID, "role": "assistant",
                "time": {"created": turn_start + 1000},
                "modelID": "m", "providerID": "p", "mode": "build",
                "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
            }}, "evt_turn3_asst", base, observed_ms=turn_start + 1000),
        ],
        settings,
    )
    # A later event for the same still-open message, observed 5 minutes on - simulates a
    # long tool call inside it still reporting progress, without the message itself (or the
    # turn) ever having completed yet.
    write_batch(
        conn,
        [
            _envelope(9103, "message.part.updated", {"part": {
                "type": "step-start", "id": "prt_turn3_step", "messageID": "msg_asst_003",
            }}, "evt_turn3_step", base, observed_ms=turn_start + 1000 + five_minutes),
        ],
        settings,
    )

    row = dict(conn.execute("SELECT duration_ms, unaccounted_ms FROM sessions WHERE id = ?", (SID,)).fetchone())

    # The live turn's span should stretch close to the ~5 minutes we know elapsed (via
    # last_observed_ms), not freeze at ~1s (assistant start - user start).
    assert row["duration_ms"] >= 22500 + five_minutes - 5_000
    # And that whole open stretch should count as covered (the message is "busy", not
    # "unaccounted"), not balloon unaccounted_ms by anywhere near the 5 minutes added.
    assert row["unaccounted_ms"] < 30_000


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
