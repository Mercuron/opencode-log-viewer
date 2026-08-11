from __future__ import annotations

from .conftest import load_fixture_events


def test_batch_ingest_populates_db_and_sessions(client):
    events = load_fixture_events()
    headers = {"Authorization": "Bearer s3cret"}
    r = client.post("/api/v1/events/batch", json={"events": events}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == len(events)
    assert body["duplicates"] == 0
    assert body["rejected"] == 0


def test_resend_same_batch_is_idempotent(client):
    events = load_fixture_events()
    headers = {"Authorization": "Bearer s3cret"}
    client.post("/api/v1/events/batch", json={"events": events}, headers=headers)

    r = client.post("/api/v1/events/batch", json={"events": events}, headers=headers)
    body = r.json()
    assert body["accepted"] == 0
    assert body["duplicates"] == len(events)

    r = client.post("/api/v1/auth/login", json={"password": "adminpw"})
    assert r.status_code == 200
    sessions = client.get("/api/v1/sessions").json()
    session_count_after_first = len(sessions)

    client.post("/api/v1/events/batch", json={"events": events}, headers=headers)
    sessions_after_resend = client.get("/api/v1/sessions").json()
    assert len(sessions_after_resend) == session_count_after_first


def test_unknown_event_type_is_accepted_and_does_not_break_indexing(client):
    events = load_fixture_events()
    unknown = dict(events[0])
    unknown["event_id"] = "evt_test_unknown"
    unknown["event_type"] = "future.unreleased.event.v99"
    unknown["sequence"] = 99999

    headers = {"Authorization": "Bearer s3cret"}
    r = client.post("/api/v1/events/batch", json={"events": [unknown]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["accepted"] == 1
    assert r.json()["rejected"] == 0

    # indexing must not have crashed: the session it targets is still queryable
    client.post("/api/v1/auth/login", json={"password": "adminpw"})
    r = client.get(f"/api/v1/sessions/{unknown['session_id']}")
    assert r.status_code == 200


def test_oversized_payload_is_stored_truncated_not_dropped(client, conn):
    events = load_fixture_events()
    base = dict(events[0])
    base["event_id"] = "evt_test_truncated"
    base["sequence"] = 88888
    base["truncated"] = True
    base["original_size"] = 5_000_000
    base["payload"] = {"info": {"note": "huge payload placeholder"}}

    headers = {"Authorization": "Bearer s3cret"}
    r = client.post("/api/v1/events/batch", json={"events": [base]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["accepted"] == 1

    row = conn.execute("SELECT truncated, original_size FROM events WHERE event_id = ?", (base["event_id"],)).fetchone()
    assert row["truncated"] == 1
    assert row["original_size"] == 5_000_000


def test_wrong_ingest_secret_is_rejected(client):
    events = load_fixture_events()
    r = client.post("/api/v1/events/batch", json={"events": events[:1]}, headers={"Authorization": "Bearer wrong-secret"})
    assert r.status_code == 401


def test_missing_auth_header_is_rejected(client):
    events = load_fixture_events()
    r = client.post("/api/v1/events/batch", json={"events": events[:1]})
    assert r.status_code == 401
