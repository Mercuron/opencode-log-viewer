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
