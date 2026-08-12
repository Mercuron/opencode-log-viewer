from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .conftest import load_fixture_events

SID = "ses_00fdbcb3affezdUs1su8KIvq3b"


def _login(client):
    assert client.post("/api/v1/auth/login", json={"password": "adminpw"}).status_code == 200


def test_storage_endpoint_reports_db_size(client):
    _login(client)
    r = client.get("/api/v1/admin/storage")
    assert r.status_code == 200
    assert r.json()["db_size_bytes"] > 0


def test_cleanup_estimate_does_not_delete_anything(client, conn):
    events = load_fixture_events()
    client.post("/api/v1/events/batch", json={"events": events}, headers={"Authorization": "Bearer s3cret"})
    _login(client)

    r = client.post("/api/v1/admin/cleanup/estimate", json={"older_than_days": 0})  # "older than now" = everything
    assert r.status_code == 200
    assert r.json()["sessions_count"] >= 1
    assert r.json()["estimated_bytes"] > 0

    still_there = client.get(f"/api/v1/sessions/{SID}")
    assert still_there.status_code == 200


def test_merge_sources_moves_sessions_and_events_and_drops_old_source(client, conn):
    events = load_fixture_events()
    client.post("/api/v1/events/batch", json={"events": events}, headers={"Authorization": "Bearer s3cret"})
    _login(client)

    # Simulate the real-world bug being fixed: the same physical agent shows up as a second
    # source (e.g. after a container recreation changed its hostname-derived id).
    conn.execute(
        "INSERT INTO sources (id, name, first_seen_at, last_seen_at) VALUES ('dupe-source', 'dupe', datetime('now'), datetime('now'))"
    )
    conn.execute("UPDATE sessions SET source_id = 'dupe-source' WHERE id = ?", (SID,))
    conn.execute("UPDATE events SET source_id = 'dupe-source' WHERE session_id = ?", (SID,))

    original_source_id = "2e54c62eb839a837"
    r = client.post("/api/v1/admin/sources/merge", json={"from_id": "dupe-source", "into_id": original_source_id})
    assert r.status_code == 200
    body = r.json()
    assert body["sessions_moved"] >= 1
    assert body["events_moved"] >= 1

    assert conn.execute("SELECT source_id FROM sessions WHERE id = ?", (SID,)).fetchone()["source_id"] == original_source_id
    assert conn.execute("SELECT COUNT(*) c FROM events WHERE source_id = 'dupe-source'").fetchone()["c"] == 0
    assert conn.execute("SELECT * FROM sources WHERE id = 'dupe-source'").fetchone() is None


def test_merge_sources_rejects_unknown_or_identical_ids(client, conn):
    _login(client)
    r = client.post("/api/v1/admin/sources/merge", json={"from_id": "does-not-exist", "into_id": "also-not-real"})
    assert r.status_code == 404

    conn.execute(
        "INSERT INTO sources (id, name, first_seen_at, last_seen_at) VALUES ('only-one', 'x', datetime('now'), datetime('now'))"
    )
    r = client.post("/api/v1/admin/sources/merge", json={"from_id": "only-one", "into_id": "only-one"})
    assert r.status_code == 400


def test_cleanup_execute_deletes_old_sessions_only(client, conn):
    events = load_fixture_events()
    client.post("/api/v1/events/batch", json={"events": events}, headers={"Authorization": "Bearer s3cret"})
    _login(client)

    # Fixture timestamps are a fixed synthetic epoch, not "now" - the other
    # session in these fixtures would also look >90 days old by wall-clock
    # time otherwise. Pin it recent so this test isolates the one session
    # deliberately aged below.
    recent_iso = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    conn.execute("UPDATE sessions SET created_at = ? WHERE id != ?", (recent_iso, SID))

    old_iso = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    conn.execute("UPDATE sessions SET created_at = ? WHERE id = ?", (old_iso, SID))

    r = client.post("/api/v1/admin/cleanup/execute", json={"older_than_days": 90})
    assert r.status_code == 200
    assert r.json()["deleted_sessions"] == 1

    assert client.get(f"/api/v1/sessions/{SID}").status_code == 404
